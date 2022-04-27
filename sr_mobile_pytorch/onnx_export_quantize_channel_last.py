import torch
import torch.nn as nn
from onnxruntime.quantization import quantize_dynamic, QuantType

from sr_mobile_pytorch.model import AnchorBasedPlainNet


class AnchorBasedPlainNetChannelLast(nn.Module):
    def __init__(self, model_checkpoint: str):
        super(AnchorBasedPlainNetChannelLast, self).__init__()
        self.weights = torch.load(model_checkpoint, map_location=torch.device("cpu"))
        self.abpn = AnchorBasedPlainNet()
        self.abpn.load_state_dict(self.weights, strict=True)
        self.abpn.eval()

    def forward(self, x):
        return self.abpn(torch.permute(x, (0, 3, 1, 2)))


def main():
    model_checkpoint = "./experiments/generator_v4_channel_last/model_channel_last.pth"
    onnx_model_name = model_checkpoint.replace("pth", "onnx")
    quantized_model_name = model_checkpoint.replace("pth", "quant.onnx")

    model = AnchorBasedPlainNetChannelLast(model_checkpoint)
    model.eval()

    dummy_input = torch.randn(1, 160, 100, 3, requires_grad=True)

    with torch.no_grad():
        output_tensor = model(dummy_input)
        print(output_tensor.shape)

    torch.onnx.export(
        model,
        dummy_input,
        onnx_model_name,
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size", 1: "height", 2: "width"},
            "output": {0: "batch_size", 1: "height", 2: "width"},
        },
    )

    quantize_dynamic(
        onnx_model_name, quantized_model_name, weight_type=QuantType.QUInt8
    )


if __name__ == "__main__":
    main()
