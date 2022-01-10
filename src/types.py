import random
from difflib import get_close_matches
from os import path, listdir

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import io, transform

from .common import Sampler, embed_in_image, beta_distribution, to_image


class Artefact:
    """This class represents a collection of artefacts of one type, usually originating from one source
    image, as described in the `data/artefacts/meta.json` file. This class holds all necessary information to be called
    in order to insert artefacts in an image.

    All specializations of this class represent other types of artefacts, and therefore other mechanism to
    insert them into a given image. E.g. it performs different augmentation strategies and different location
    of insertion.

    In an effort to make results reproducible a seed can be set. This will affect all processes affected by randomness
    in this class and used functions.
    """

    def __new__(cls, json_string, artefacts_path, seed=None):
        """Instantiation of this class will provide some sort of factory behavior, meaning
        depending on the given json object (specifically on the class and subclass field) the
        corresponding object will be returned.
        """
        if json_string['class'] == "bubble":
            return super().__new__(Bubble)
        elif json_string['class'] == "marking":
            if json_string['subclass'] == "circle":
                return super().__new__(MarkingCircle)
            elif json_string['subclass'] == "spot":
                return super().__new__(MarkingSpot)
        elif json_string['class'] == "ruler":
            if json_string['subclass'] == "horizontal":
                return super().__new__(RulerHorizontal)
            elif json_string['subclass'] == "vertical":
                return super().__new__(RulerVertical)
        raise NotImplementedError("no matching class found.")

    def __init__(self, json_string, artefacts_path, seed=None):
        """Default init function tries to load artefacts according to the given json string.
        See the example meta.json the expected structure of data.
        Also some default parameters for artefact augmentation and transformations are set.

        :param json_string:
        :param artefacts_path:
        """
        self.json = json_string
        self._random = random.Random(seed)
        self._artefact_folder = path.join(artefacts_path, json_string['artefact_folder'])
        self._artefact_images = []

        # load artefact images
        paths = [f for f in listdir(self._artefact_folder) if path.splitext(f)[1] in ['.png', '.jpg', '.jpeg', '.gif']]
        if json_string.get('preprocessor') is not None and json_string.get('preprocessor') in "difference":
            # find with and coresponding without images
            paths_without = [f for f in paths if 'without' in f]
            paths_with = [f for f in paths if f not in paths_without]
            path_pairs = [(f, get_close_matches(f.replace('with', 'without'), paths_without, n=1, cutoff=0)[0]) for f in
                          paths_with]
            for pwith, pwithout in path_pairs:
                im_with = np.array(Image.open(path.join(self._artefact_folder, pwith)))
                im_with = im_with[:, :, 0:3]
                im_without = io.imread(path.join(self._artefact_folder, pwithout))
                self._artefact_images.append(np.subtract(im_with, im_without, dtype='int16'))
        else:
            for path_im in paths:
                im = np.array(Image.open(path.join(self._artefact_folder, path_im)))
                self._artefact_images.append(np.subtract(im, np.full(im.shape, 255, dtype='int16')))

        # save number of artefacts
        self.json['number_of_artefacts'] = len(self._artefact_images)

        # cache probability distribution function later
        self._dpdf_cache = None

        # values used to perform random transformations and augmentations before
        # artefacts are inserted into an image
        # child classes will overwrite those values
        self._augment = {"replicate_prob": .5,
                         "remove_prob": .5}
        self._transform = {"flip_prob": .5,
                           "resize_prob": .5,
                           "resize_scaling_range": [.5, 1.5],
                           "rotate_prob": .5,
                           "rotate_range": [0, 359]}

    def __repr__(self):
        return str(self.json)

    def __call__(self, image, mask=None):
        """This function takes the image object and inserts artefacts in the image, the position
        of artefacts can be influenced by the given mask object. This implementation is
        specific to the type of the artefact (see implementations in child classes).
        The position of the insertions of artefacts is chosen in a way that there
        is as little overlap as possible between artefacts, and if a (lesion-)mask is given,
        between artefacts and mask.

        :param image: PIL Image object
        :param mask: mask
        :returns image: PIL Image with inserted artefacts
        """

        # convert image and mask
        image = np.array(image, dtype='int16')
        if mask:
            mask = np.array(mask, dtype='uint8')

        # obtain dpdf if not done or image does not fit
        if self._dpdf_cache is None or self._dpdf_cache.shape != image.shape:
            self._dpdf_cache = beta_distribution(image.shape)  # obtain the beta continuous probability distribution

        # if lesion mask is available, "remove" lesion region from dpdf array
        if mask is not None:
            mask_blurred = ndimage.gaussian_filter(mask[:, :], sigma=15)  # smooth the mask
            mask_blurred = (mask_blurred.astype(float) / -255) + 1  # normalize [0,1] and invert
            dpdf = np.multiply(self._dpdf_cache, mask_blurred)  # remove region of lesion from dpdf by multiplying
        else:
            dpdf = self._dpdf_cache

        # obtain sampler for this image
        sampler = Sampler(dpdf, seed=self._random.random())

        # get current selection of (possibly randomly varied) artefacts
        # this function should be overwritten by each subclass
        artefact_selection = self._get_random_artefacts()

        # place artefacts in image with no overlap if possible (try a certain number - 10 times)
        used_locations = np.ndarray(image.shape, dtype=np.bool)
        for artefact in artefact_selection:
            num_attempts = 0
            while num_attempts < 10:  # try a maximum of 10 times
                num_attempts += 1
                pos = sampler.rand2d()  # get random position
                pos_start = np.subtract(pos,
                                        (np.floor(np.divide(artefact.shape[0:2], 2)).astype(int)))  # top left corner
                pos_end = (np.add(pos_start, artefact.shape[0:2])).astype(int)  # bottom right corner position

                # if no overlap between artefacts would occur
                if not used_locations[pos_start[0]:pos_end[0], pos_start[1]:pos_end[1]].any():
                    used_locations[pos_start[0]:pos_end[0], pos_start[1]:pos_end[1]] = True  # remember occupied area
                    image = embed_in_image(image, artefact, pos)  # place artefact in image
                    num_attempts = 10

        return to_image(image)

    def _get_random_artefacts(self):
        """Selects some artefacts out of all available ones, according to the specifications set in
        self._augment. Then it applies random transformations controlled by self._transform on each
        of those artefacts and then returns a list of those.

        :return List of artefacts
        """

        # select artefacts
        tmp = [np.copy(x) for x in self._artefact_images if self._random.random() > self._augment['remove_prob']]
        # but ensure that at least one is selected
        if len(tmp) < 1:
            tmp.append(np.copy(self._artefact_images[0]))

        # duplicate artefacts
        tmp.extend([np.copy(i) for i in tmp if self._random.random() < self._augment['replicate_prob']])

        # alter artefacts
        for i, t in enumerate(tmp):
            # flip
            if self._random.random() < self._transform['flip_prob']:
                t = np.flip(t, axis=self._random.random() > .5)

            # resize
            if self._random.random() < self._transform['resize_prob']:
                new_dimensions = np.floor(np.multiply(t.shape[0:2],
                                                      self._random.uniform(self._transform['resize_scaling_range'][0],
                                                                           self._transform['resize_scaling_range'][1])))
                new_dimensions = np.append(new_dimensions, t.shape[2])
                t = transform.resize(t, new_dimensions, preserve_range=True, anti_aliasing=True)
                t = t.astype(t.dtype)

            # rotate
            if self._random.random() < self._transform['rotate_prob']:
                t = transform.rotate(t, angle=self._random.randint(self._transform['rotate_range'][0],
                                                                   self._transform['rotate_range'][1]),
                                     resize=True,
                                     mode='constant', cval=0, preserve_range=True)
                t = t.astype(t.dtype)
            tmp[i] = t

        return tmp


class Bubble(Artefact):
    """Represents artefacts of type bubble."""

    def __init__(self, json_string, artefacts_path, seed=None):
        super().__init__(json_string, artefacts_path, seed)

        self._augment.update({"replicate_prob": .8,
                              "remove_prob": .1})


class Marking(Artefact):
    pass


class MarkingCircle(Marking):
    """Represents ink markings that are arranged around a lesion, or look like circle around a lesion."""

    def __init__(self, json_string, artefacts_path, seed=None):
        super().__init__(json_string, artefacts_path, seed)

        self._augment.update({"replicate_prob": 0,
                              "remove_prob": 0})
        self._transform.update({"resize_prob": .8,
                                "resize_scaling_range": [.8, 1.4],
                                "rotate_prob": .9})

    def __call__(self, image, mask=None):
        """Artefacts of this class are always oriented around the region of lesion,

        :param image:
        :param mask:
        :return:
        """

        # convert image
        image = np.array(image, dtype='int16')

        # if mask is available use its center, otherwise use the center of the image
        if mask is not None:
            mask = np.array(mask, dtype='uint8')
            pos = ndimage.center_of_mass(mask)
            pos = [int(pos[0]), int(pos[1])]
        else:
            pos = (np.divide(image.shape[0:2], 2)).astype(np.int)

        # transform the image ...
        artefact_selection = self._get_random_artefacts()

        # ... and place it there
        image = embed_in_image(image, artefact_selection[0], pos)
        return to_image(image)


class MarkingSpot(Marking):
    """Represents ink markings occurring somewhere next to the lesion, similar to bubble artefacts."""

    def __init__(self, json_string, artefacts_path, seed=None):
        super().__init__(json_string, artefacts_path, seed)

        self._augment.update({"replicate_prob": .8,
                              "remove_prob": .3})


class Ruler(Artefact):
    pass


class RulerHorizontal(Ruler):
    """Horizontal Rulers are arranged under an lesion and mostly centered at the lesion."""

    def __init__(self, json_string, artefacts_path, seed=None):
        super().__init__(json_string, artefacts_path, seed)

        self._augment.update({"replicate_prob": 0,
                              "remove_prob": 0})
        self._transform.update({"flip_prob": 0,
                                "rotate_prob": 1,
                                "rotate_range": [-20, 20]})

    def __call__(self, image, mask=None):

        # convert image
        image = np.array(image, dtype='int16')
        if mask:
            mask = np.array(mask, dtype='uint8')

        # only consider the middle (1/3 of the imagewith), if available (under the lesion image and in the lower 1/3
        #  section of the image)
        middle_mask = np.zeros(image.shape[0:2], dtype=np.bool)
        middle_mask[int(middle_mask.shape[0] / 3 * 2):int(middle_mask.shape[0]),
                    int(middle_mask.shape[1] / 3):int(middle_mask.shape[1] / 3 * 2)] = True

        # if lesion mask is available, "remove" lesion region from dpdf array
        if mask is not None and np.max(mask) > 0:
            mask_blurred = ndimage.gaussian_filter(mask[:, :], sigma=15)  # smooth the mask
            mask = mask_blurred / np.max(mask_blurred)  # normalize [0,1]
            mask = mask * -1 + 1
            mask[~middle_mask] = 0  # remove middle mask areas from image_mask

        if mask is None or np.max(mask) == 0:  # in case to much is removed above or empty mask was given
            mask = middle_mask.astype(np.float16)

        # obtain dpdf if not done or image does not fit
        if self._dpdf_cache is None or self._dpdf_cache.shape != image.shape:
            self._dpdf_cache = beta_distribution(image.shape)  # obtain the beta continuous probability distribution

        # obtain the sampler with modified dpdf (mask removed)
        sampler = Sampler(np.multiply(self._dpdf_cache, mask), seed=self._random.random())

        # get current selection of (possibly randomly varied) artefacts
        artefact_selection = self._get_random_artefacts()

        for artefact in artefact_selection:
            pos = sampler.rand2d()  # get random position
            image = embed_in_image(image, artefact, pos)  # place artefact in image

        return to_image(image)


class RulerVertical(Ruler):
    """'Vertical' rulers are arranged in peripheral regions of the image, often in its corners."""

    def __init__(self, json_string, artefacts_path, seed=None):
        super().__init__(json_string, artefacts_path, seed)

        self._augment.update({"replicate_prob": 0,
                              "remove_prob": 0})
        self._transform.update({"rotate_prob": 1})

    def __call__(self, image, mask=None):

        # convert image
        image = np.array(image, dtype='int16')

        # as the mask is used in the next step, generate one if no mask was given
        # this mask will have an circular shape centered in the middle of the image
        if mask:
            mask = np.array(mask, dtype='uint8')
        else:
            x = np.linspace(-2.0, 2.0, image.shape[1])
            y = np.linspace(-2.0, 2.0, image.shape[0])
            x, y = np.meshgrid(x, y)
            r = np.sqrt((x - 0.0) ** 2 + (y - 0.0) ** 2)
            mask = (r < 1).astype(np.uint8) * np.iinfo(np.uint8).max

        # obtain dpdf if not done or image does not fit
        if self._dpdf_cache is None or self._dpdf_cache.shape != image.shape:
            self._dpdf_cache = beta_distribution(image.shape)  # obtain the beta continuous probability distribution

        # "remove" lesion region from dpdf array
        mask_blurred = ndimage.gaussian_filter(mask[:, :], sigma=15)  # smooth the mask
        mask_blurred = (mask_blurred.astype(float) / -255) + 1  # normalize [0,1] and invert
        dpdf_tmp = np.multiply(self._dpdf_cache, mask_blurred)  # remove region of lesion from dpdf by multiplying

        # place artefacts in image with no overlap with the lesion if possible
        # (try a certain number - 25 times)
        sampler = Sampler(dpdf_tmp, seed=self._random.random())

        # get current selection of (possibly randomly varied) artefacts
        artefact_selection = self._get_random_artefacts()

        for artefact in artefact_selection:
            num_attempts = 0
            while True:
                num_attempts += 1
                pos = sampler.rand2d()  # get random position

                # check if the artefact would intersect with the lesion mask
                artefact_image_sized = embed_in_image(np.zeros(image.shape, dtype=image.dtype), artefact, pos)
                artefact_image_sized_bool = np.logical_or.reduce(artefact_image_sized, axis=2)
                mask_bool = mask.astype(bool)
                intersection = artefact_image_sized_bool & mask_bool
                if not np.any(intersection) or num_attempts > 25:
                    image = embed_in_image(image, artefact, pos)  # place artefact in image
                    break

        return to_image(image)
