# This script handles the creation of artefacts for the whole of the HAM10000 dataset, it will take each image in the
# specified folder and create a new folder for it with new versions of the image, each with one artefacts inserted
# from one of the artefact types.

from shutil import copyfile
from PIL import Image
from tqdm import tqdm
import sys
import os
from os.path import join

from repository import ArtefactsRepository
from src.types import Bubble, Marking, Ruler

# Settings
# For test images, use data for example from https://challenge.kitware.com/#phase/5abcb19a56357d0139260e53
SOURCE_IMAGES_DIR = '../data/test_images/'
SOURCE_MASKS_DIR = '../data/test_masks/'
TARGET_DIR = '../data/dataset_with_artefacts/'
ARTEFACTS_META_FILE = '../data/artefacts/meta.json'


# Check Paths (if exists)
if not os.path.exists(SOURCE_IMAGES_DIR):
    sys.stderr.write(f'Path {SOURCE_IMAGES_DIR} not found.')
    sys.exit(-1)
if SOURCE_MASKS_DIR is not None and not os.path.exists(SOURCE_MASKS_DIR):
    sys.stderr.write(f'Path {SOURCE_MASKS_DIR} not found.')
    sys.exit(-1)
if not os.path.exists(TARGET_DIR):
    os.mkdir(TARGET_DIR)
    print(f'Target {TARGET_DIR} created.')


# Obtain list of source files
def scan_dir(dir_to_scan, ext):
    files = []
    for (dirpath, dirnames, filenames) in os.walk(dir_to_scan):
        files.extend([os.path.join(dirpath, f)
                      for f in filenames
                      if os.path.splitext(f)[1] in ext])
    return files


image_extensions = ['.jpg', '.jpeg', '.gif', '.png']
source_files = scan_dir(SOURCE_IMAGES_DIR, image_extensions)
print(f'Registered {len(source_files)} images for processing.')

# Obtain list of mask files
mask_files = scan_dir(SOURCE_MASKS_DIR, image_extensions)
print(f'Registered {len(mask_files)} masks for processing.')


# Match images and masks
print(f'Matching images to its masks:')
source_pairs = []
mask_names = [os.path.splitext(os.path.basename(m))[0] for m in mask_files]
for file in tqdm(source_files):
    source_name = os.path.splitext(os.path.basename(file))[0]
    pair = (file, None)
    for i, m in enumerate(mask_names):
        if source_name in m:
            pair = (file, mask_files[i])
            break
    source_pairs.append(pair)
del mask_files, mask_names, source_files, image_extensions
print(f'Matched {len([s for s in source_pairs if s[1] is not None])} images to its masks.')

# Copy all images and masks to the target directory
print(f'Copy images and masks to target directory.')
for i, (image, mask) in enumerate(tqdm(source_pairs)):
    image_target = os.path.join(TARGET_DIR, os.path.basename(image))
    copyfile(image, image_target)

    mask_folder = os.path.join(TARGET_DIR, os.path.splitext(os.path.basename(image))[0])
    if not os.path.exists(mask_folder):
        os.mkdir(mask_folder)

    if mask:
        mask_target = os.path.join(mask_folder, 'mask'+os.path.splitext(os.path.basename(mask))[1])
        copyfile(mask, mask_target)
    else:
        mask_target = None

    source_pairs[i] = (image_target, mask_target, mask_folder)
print(f'Images and masks copied.')

# Obtain ArtefactsRepository
repository = ArtefactsRepository(ARTEFACTS_META_FILE)
artefact_classes = [('bubble.png', Bubble),
                    ('ruler.png', Ruler),
                    ('marking.png', Marking)]

# Insert artefacts
print(f'Inserting artefacts.')
for image_path, mask_path, target_folder in tqdm(source_pairs):

    image = Image.open(image_path)
    mask = Image.open(mask_path) if mask_path else None

    for class_name, class_ident in artefact_classes:
        target = repository.get_random_instance(class_ident)(image, mask)
        target.save(join(target_folder, class_name), 'png', compress_level=1)

print("\ndone. bye")
