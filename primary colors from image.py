from PIL import Image
import numpy as np
import os

# Input
input_file = "input.png"
output_dir = "channels_output"
os.makedirs(output_dir, exist_ok=True)

# Load image
img = Image.open(input_file).convert("RGB")
arr = np.array(img).astype(np.uint8)

# Split RGB channels
R = arr[:, :, 0]
G = arr[:, :, 1]
B = arr[:, :, 2]

# Save grayscale channel images
Image.fromarray(R).save(os.path.join(output_dir, "red_channel.png"))
Image.fromarray(G).save(os.path.join(output_dir, "green_channel.png"))
Image.fromarray(B).save(os.path.join(output_dir, "blue_channel.png"))

print("Saved RGB channels.")