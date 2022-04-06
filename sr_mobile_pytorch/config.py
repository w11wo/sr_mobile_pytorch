model_args = {
    "scale": 4,
    "in_channels": 3,
    "num_feature": 28,
    "num_encoder": 4,
    "out_channels": 3,
}

training_args = {
    "patch_size": 64,
    "train_batch_size": 32,
    "test_batch_size": 32,
    "test_size": 0.1,
    "learning_rate": 1e-3,
    "weight_decay": 0.0,
    "warmup_ratio": 0.1,
    "epochs": 100,
    "seed": 42,
    "project": "sr_mobile",
    "entity": "w11wo",
    "outdir": "experiments",
    "data_hr": "data/train_HR",
    "data_lr": "data/train_LR/X4",
}