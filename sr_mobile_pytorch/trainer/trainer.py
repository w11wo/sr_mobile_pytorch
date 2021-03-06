import os
import torch
import torch.nn.functional as F
from torch.nn import L1Loss
from torch.utils.data import DataLoader
from torch.optim import Adam
from tqdm.auto import tqdm
import wandb

from sr_mobile_pytorch.model import AnchorBasedPlainNet
from sr_mobile_pytorch.trainer.schedulers import get_linear_schedule_with_warmup
from sr_mobile_pytorch.trainer.metrics import calculate_psnr
from sr_mobile_pytorch.trainer.utils import seed_everything, logger
from sr_mobile_pytorch.trainer.losses import ContentLossResNetSimCLR


class Trainer:
    def __init__(self, model_args, training_args, train_dataset, test_dataset):
        seed_everything(training_args["seed"])
        self.model_args = model_args
        self.training_args = training_args

        self.train_loader = DataLoader(
            dataset=train_dataset,
            batch_size=training_args["train_batch_size"],
            shuffle=True,
            num_workers=training_args["num_workers"],
        )

        self.test_loader = DataLoader(
            dataset=test_dataset,
            batch_size=1,
            shuffle=False,
            num_workers=training_args["num_workers"],
        )

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = AnchorBasedPlainNet(**model_args)
        self.model = self.model.to(self.device)

        self.pixelwise_loss = L1Loss()
        self.content_loss = ContentLossResNetSimCLR(
            training_args["resnet_weights"], self.device
        )
        self.optimizer = Adam(
            self.model.parameters(),
            training_args["learning_rate"],
            weight_decay=training_args["weight_decay"],
        )

        num_training_steps = len(self.train_loader) * training_args["epochs"]
        warmup_steps = int(training_args["warmup_ratio"] * num_training_steps)
        self.scheduler = get_linear_schedule_with_warmup(
            self.optimizer, warmup_steps, num_training_steps, last_epoch=-1
        )

        self.state = {"best_psnr": None, "best_loss": None}
        wandb.watch(self.model)

    def fit(self):
        for epoch in range(self.training_args["epochs"]):
            epoch_content_loss, epoch_pixelwise_loss = 0.0, 0.0
            epoch_perceptual_loss = 0.0
            self.model.train()

            for lr, hr in tqdm(self.train_loader, total=len(self.train_loader)):
                lr, hr = lr.to(self.device), hr.to(self.device)

                self.optimizer.zero_grad()
                sr = self.model(lr)

                pixelwise_loss = self.pixelwise_loss(sr, hr)
                content_loss = self.content_loss(hr, sr)
                perceptual_loss = content_loss + pixelwise_loss

                perceptual_loss.backward()

                self.optimizer.step()
                self.scheduler.step()

                epoch_pixelwise_loss += pixelwise_loss.item()
                epoch_content_loss += content_loss.item()
                epoch_perceptual_loss += perceptual_loss.item()

            train_content_loss = epoch_content_loss / len(self.train_loader)
            train_pixelwise_loss = epoch_pixelwise_loss / len(self.train_loader)
            train_perceptual_loss = epoch_perceptual_loss / len(self.train_loader)
            test_loss, test_psnr = self.evaluate()

            self.save_best_model(test_loss, test_psnr)
            self.report_results(
                train_content_loss,
                train_pixelwise_loss,
                train_perceptual_loss,
                test_loss,
                test_psnr,
                epoch + 1,
            )

            logger.info(
                f"Epoch: {epoch:4} | Train Content Loss: {train_content_loss:.4f} | Train Pixelwise Loss: {train_pixelwise_loss:.4f} | Train Perceptual Loss: {train_perceptual_loss:.4f} | Test Loss: {test_loss:.4f} | PSNR: {test_psnr:.2f}"
            )

    def evaluate(self):
        total_loss, total_psnr = 0.0, 0.0
        self.model.eval()

        with torch.no_grad():
            for lr, hr in tqdm(self.test_loader, total=len(self.test_loader)):
                lr, hr = lr.to(self.device), hr.to(self.device)

                sr = self.model(lr)

                loss = self.pixelwise_loss(sr, hr)
                total_psnr += calculate_psnr(
                    sr.cpu().detach().numpy(), hr.cpu().detach().numpy()
                )
                total_loss += loss.item()

            test_loss = total_loss / len(self.test_loader)
            test_psnr = total_psnr / len(self.test_loader)

            return test_loss, test_psnr

    def report_results(
        self,
        train_content_loss,
        train_pixelwise_loss,
        train_perceptual_loss,
        test_loss,
        test_psnr,
        step,
    ):
        wandb.log(
            {
                "train-content-loss": train_content_loss,
                "train-pixelwise-loss": train_pixelwise_loss,
                "train-perceptual-loss": train_perceptual_loss,
                "test-pixelwise-loss": test_loss,
                "test-psnr": test_psnr,
            },
            step=step,
        )

    def save_best_model(self, current_loss, current_psnr):
        save_path = f"{self.training_args['outdir']}/generator"
        os.makedirs(save_path, exist_ok=True)

        torch.save(self.model.state_dict(), f"{save_path}/model.pth")

        if self.state["best_loss"] == None or current_loss < self.state["best_loss"]:
            self.state["best_loss"] = current_loss
            torch.save(self.model.state_dict(), f"{save_path}/best_loss.pth")

        if self.state["best_psnr"] == None or current_psnr > self.state["best_psnr"]:
            self.state["best_psnr"] = current_psnr
            torch.save(self.model.state_dict(), f"{save_path}/best_psnr.pth")

