import torch
import torch.nn as nn

from sr_mobile_pytorch.trainer.utils import imagenet_normalize


class ContentLoss(nn.Module):
    def __init__(self, device):
        super().__init__()
        self.device = device
        self.mse_loss = nn.MSELoss()
        self.vgg = torch.hub.load("pytorch/vision:v0.10.0", "vgg19", pretrained=True)
        self.model = nn.Sequential(*[self.vgg.features[i] for i in range(36)]).eval()
        for param in self.model.parameters():
            param.requires_grad = False
        self.model = self.model.to(device)

    def forward(self, hr, sr):
        sr = imagenet_normalize(sr)
        hr = imagenet_normalize(hr)
        sr_features = self.model(sr) / 12.75
        hr_features = self.model(hr) / 12.75
        return self.mse_loss(hr_features, sr_features)


class GANLoss:
    def __init__(self):
        self.bce_loss = nn.BCEWithLogitsLoss()

    def generator_loss(self, sr_out):
        return self.bce_loss(sr_out, torch.ones_like(sr_out))

    def discriminator_loss(self, hr_out, sr_out):
        hr_loss = self.bce_loss(hr_out, torch.ones_like(hr_out))
        sr_loss = self.bce_loss(sr_out, torch.zeros_like(sr_out))
        return hr_loss + sr_loss
