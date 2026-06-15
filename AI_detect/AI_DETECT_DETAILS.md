# SmartRoast AI Detection Pipeline

## Overview

This module adds the first camera-based AI workflow for the Smart Coffee Roaster project.

The system is designed for a Raspberry Pi 4B connected to a Raspberry Pi camera. The camera is mounted in a fixed position and captures images from inside the roasting chamber. The software crops a fixed region of interest, detects whether coffee beans are present, and then calculates the average grayscale value of the cropped bean region.

The grayscale value is used as an early roast colour indicator. As roasting progresses, the bean region is expected to become darker, so images captured later in the same batch should generally show a lower average grayscale value.

---

## Project Goals

* Test Raspberry Pi camera capture and image-processing behaviour
* Collect real roast image data with batch-aware file names
* Crop a fixed bean region from each captured image
* Prepare labelled datasets for bean/no-bean classification
* Apply data augmentation only to the training set
* Train and compare several lightweight CNN models using PyTorch
* Save the best-performing model locally
* Calculate average grayscale values for roast monitoring
* Generate per-batch grayscale trend plots

---

## Folder Structure

```text
AI_detect/
  01_full_system_test.py      # One-command camera and image-processing test
  02_auto_capture.py          # Timed automatic image capture during roasting
  03_crop_images.py           # Fixed ROI cropping for all captured images
  04_split_dataset.py         # 8:1:1 train/validation/test dataset split
  05_augment_train_set.py     # Training-set-only data augmentation
  06_train_models.py          # PyTorch CNN training and model comparison
  07_plot_gray_trend.py       # Per-batch grayscale trend plotting
  08_predict_image.py         # Single-image model inference
  09_pi_camera_inference.py   # CLI wrapper for live Raspberry Pi inference
  10_test_detector_loop.py    # Reusable detector loop test
  camera_utils.py             # Picamera2, OpenCV, and mock camera helpers
  grayscale_utils.py          # Reusable average grayscale calculation
  model_utils.py              # Shared CNN model definition
  pi_ai_detector.py           # Reusable detector class for backend integration
  model_config.json           # CNN architecture and training configuration
  requirements.txt            # Python dependencies
  raw/                        # Original captured images
  resized/                    # Cropped ROI images
  train_set/
  validate_set/
  test_set/
  train_set_augmented/
  models/
  plot/
  test_outputs/
```

The generated image data, plots, and model weights are ignored by `AI_detect/.gitignore` so that large local files are not committed accidentally.

---

## Technologies Used

* Raspberry Pi 4B
* Raspberry Pi camera / Picamera2
* Python
* Pillow
* NumPy
* Matplotlib
* PyTorch
* OpenCV fallback camera access

---

## Environment Setup

On Raspberry Pi OS, Picamera2 is normally installed through `apt`:

```bash
sudo apt update
sudo apt install -y python3-picamera2
```

Install the Python dependencies from this module:

```bash
cd AI_detect
python -m pip install -r requirements.txt
```

If PyTorch or OpenCV installation is slow on the Raspberry Pi, the capture, crop, grayscale, and plotting scripts can be tested first with only `Pillow`, `numpy`, and `matplotlib`. The model training script requires `torch`.

---

## Workflow

### 1. Full System Test

Run a camera and image-processing smoke test:

```bash
python 01_full_system_test.py --backend picamera2 --width 1920 --height 1080
```

For development on a laptop or on a machine without camera hardware, use the mock image generator:

```bash
python 01_full_system_test.py --mock
```

The script reports dependency availability, capture backend, image resolution, crop coordinates, grayscale output path, and the calculated mean grayscale value. Test outputs are saved in `test_outputs/`.

### 2. Automatic Data Capture

Capture images at a fixed interval during a roast:

```bash
python 02_auto_capture.py --batch-id 2026-06-08-A --interval 2 --count 180 --backend picamera2
```

Images are saved to `raw/` using batch-aware file names:

```text
batch_2026-06-08-A_shot_0001.jpg
batch_2026-06-08-A_shot_0002.jpg
```

The batch ID identifies the roast batch. The shot number identifies the image order within that batch. Use `--count 0` to keep capturing until `Ctrl+C` is pressed.

### 3. Fixed Region Cropping

After collecting a few sample images, manually inspect the frame and choose the top-left and bottom-right pixel coordinates of the bean region.

Example:

```bash
python 03_crop_images.py --x1 620 --y1 420 --x2 1280 --y2 820 --clear-output
```

To resize cropped images to a consistent CNN input size:

```bash
python 03_crop_images.py --x1 620 --y1 420 --x2 1280 --y2 820 --resize 96 96 --clear-output
```

The cropped images are saved in `resized/`, while keeping the original batch and shot naming format for later grayscale trend analysis.

### 4. Manual Labelling

The cropped images must be arranged into class folders before dataset splitting. In addition to normal bean/no-bean images, corrupted camera frames should be kept as their own class instead of being forced into either normal class:

```text
resized/
  bean/
    batch_2026-06-08-A_shot_0001.jpg
  no_bean/
    batch_empty-A_shot_0001.jpg
  corrupted/
    batch_7_shot_0330.jpg
```

At least two classes are required for training. For the current camera workflow, the recommended labels are:

* `bean` - the cropped image is valid and contains coffee beans
* `no_bean` - the cropped image is valid and does not contain coffee beans
* `corrupted` - the image is damaged, partially purple, severely blurred, overexposed, or otherwise not reliable

The `no_bean` class should include empty chamber images, startup images, and different lighting or background conditions that may occur during real operation. The `corrupted` class helps the model reject camera failures instead of treating them as valid no-bean images.

If a whole crop run belongs to one class, the crop script can place output directly into a class folder:

```bash
python 03_crop_images.py --x1 620 --y1 420 --x2 1280 --y2 820 --label bean --clear-output
```

When `--clear-output` is used without `--label`, the crop script preserves the protected label folders `bean`, `no_bean`, and `corrupted`. Root-level unlabelled crops should be moved into one of the label folders before running the split script.

### 5. Dataset Split

Split the labelled `resized/` images into training, validation, and test folders:

```bash
python 04_split_dataset.py --seed 42
```

The default split ratio is 8:1:1. The script splits each class independently and ensures that the same image is not copied into multiple datasets.

If labelled class folders and root-level unlabelled images are mixed inside `resized/`, the split script stops and asks for the root-level images to be labelled first. This prevents accidental training with incorrectly labelled data.

### 6. Data Augmentation

Generate augmented training data:

```bash
python 05_augment_train_set.py --copies-per-image 5
```

The script clears `train_set_augmented/`, copies the original training images, and adds augmented versions using small rotations, horizontal flips, light brightness variation, light Gaussian blur, and light noise. Validation and test images are not augmented so that evaluation remains realistic.

---

## Model Training

Train and compare the CNN models listed in `model_config.json`:

```bash
python 06_train_models.py
```

The training script reads:

```text
train_set_augmented/
validate_set/
test_set/
```

The training process is:

1. Train every CNN architecture defined in `model_config.json`.
2. Rank the models using validation-set performance.
3. Select the best three validation models.
4. Retrain those three models using `train_set_augmented + validate_set`.
5. Evaluate the final three models on `test_set`.
6. Save the best model to `models/best_model.pt`.
7. Save the training summary to `models/training_summary.json`.

`model_config.json` can be edited to change the input image size, batch size, number of epochs, learning rate, convolution channels, dense layers, dropout, and batch normalisation settings.

---

## Grayscale Monitoring

The average grayscale function can be imported by other scripts:

```python
from grayscale_utils import mean_grayscale

value = mean_grayscale("resized/batch_2026-06-08-A_shot_0040.jpg")
print(value)
```

The returned value is between `0` and `255`. Lower values indicate a darker image.

This should only be used as a roast-colour indicator after the image has passed the bean/no-bean classifier. If the fixed ROI does not contain beans, the grayscale value will not represent bean colour.

---

## Single Image Prediction

After training, classify one image with the saved model:

```bash
python 08_predict_image.py path/to/image.jpg --device cuda --save-debug
```

For a browser screenshot or casual phone photo that contains the camera stream inside a larger image, keep the default crop settings. The script first tries to remove the screenshot background and then applies the same centred ROI crop used by `01_full_system_test.py`.

For an original camera frame without browser UI:

```bash
python 08_predict_image.py path/to/frame.jpg --frame-crop none --roi-crop training-center --device cuda
```

For an image that is already cropped to the ROI:

```bash
python 08_predict_image.py path/to/roi.jpg --frame-crop none --roi-crop none --device cuda
```

The script prints the predicted class and probabilities for `bean`, `no_bean`, and `corrupted`. With `--save-debug`, it also saves the intermediate crops in `test_outputs/`.

---

## Raspberry Pi Deployment

The default Raspberry Pi deployment path now uses the Raspberry Pi AI Camera IMX500 `.rpk` model. Copy the converted model to:

```text
AI_detect/models/coffee_qmodel.rpk
```

The reusable detector keeps the camera and model open so inference can be called repeatedly without reloading the model:

```python
from pi_ai_detector import SmartRoastAIDetector

detector = SmartRoastAIDetector(
    model_path="AI_detect/models/coffee_qmodel.rpk",
    backend="picamera2",
)

with detector:
    result = detector.infer_once()
    print(result.to_dict())
```

The returned result includes `prediction`, class probabilities, mean grayscale, ROI coordinates, frame size, ROI size, inference time, model format, and optional crop path. This object-oriented path is the best option for backend integration.

The `09_pi_camera_inference.py` script is a command-line wrapper around the same reusable detector class. It runs the `.rpk` model by default:

```bash
python 09_pi_camera_inference.py --backend picamera2 --count 0 --interval 1 --save-crops --csv-log test_outputs/pi_inference.csv
```

The class order for the current model is expected to be:

```text
bean corrupted no_bean
```

If the exported `.rpk` uses a different output order, pass it explicitly:

```bash
python 09_pi_camera_inference.py --class-names bean corrupted no_bean
```

For laptop development or old PyTorch checkpoint testing, explicitly select the `.pt` path:

```bash
python 10_test_detector_loop.py --model-format pt --model models/best_model.pt --backend mock --count 3 --interval 2 --save-crops
```

Both scripts capture a frame, apply the fixed ROI crop for grayscale reporting, run the classifier, print class probabilities, and report the ROI mean grayscale value. If the class is `bean`, the grayscale value can be used as the roast-colour indicator. If the class is `no_bean` or `corrupted`, the grayscale value should not be used for roast-colour control.

Do not start a new Python process for every frame. Keep one `SmartRoastAIDetector` instance alive and call `infer_once()` repeatedly. Otherwise, the Raspberry Pi will repeatedly reload the `.rpk` firmware and reopen the camera.

---

## Batch Trend Plots

Generate grayscale trend plots for each roast batch:

```bash
python 07_plot_gray_trend.py
```

The script searches `resized/` for files named like:

```text
batch_<batch_id>_shot_<number>.jpg
```

For each batch, it saves:

```text
plot/batch_2026-06-08-A_gray_trend.png
plot/batch_2026-06-08-A_gray_values.csv
```

If lighting, camera position, ROI coordinates, and shot ordering are stable, later images should usually have lower grayscale values than earlier images. If a negative trend is not observed, check for glare, changing illumination, incorrect ROI selection, mixed batches, or inconsistent roast ordering.

---

## Current Status

The AI detection module currently provides the full offline workflow required to collect data, crop it, label it, split it, augment it, train candidate models, save the best model, and analyse grayscale trends.

The next integration step is to connect the saved CNN model into the live Raspberry Pi control workflow:

1. Capture a frame from the fixed camera.
2. Crop the fixed ROI.
3. Run the bean/no-bean CNN classifier.
4. If beans are detected, calculate the mean grayscale value.
5. Log grayscale, temperature, time, and batch ID together.
6. Use the combined data for roast monitoring and future AI-assisted roast optimisation.

---

## Safety Note

This module is intended to support roast monitoring. It should not replace thermal safety checks, emergency stop behaviour, or electrical safety precautions in the main coffee roaster system.
