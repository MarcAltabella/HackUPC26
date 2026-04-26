import torch
import warnings
warnings.filterwarnings("ignore")
model_dict = torch.load('models/artifacts/models/sensor_classifier.pt', weights_only=False)
print(model_dict['config'])
