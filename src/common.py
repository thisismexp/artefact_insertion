import random
from PIL import Image

import numpy as np
from scipy.special import gamma


def to_image(ndarray):
    ndarray[ndarray < 0] = 0
    ndarray[ndarray > 255] = 255
    return Image.fromarray(np.uint8(ndarray))


def embed_in_image(image_target, image_source, position):
    """This function places a smaller image in a bigger one on a given position,
    where position is given as x/y coordinate and describes the position
    of the center of the image_source in image_target.

    :param image_target: target image
    :param image_source: PIL image
    :param position: ndarrday of position (x,y)
    :return: image with inserted smaller image
    """

    image_target = np.array(image_target, dtype='int16')

    # calculate overlap top left and adjust image source
    pos_target_start = np.subtract(position, np.floor_divide(image_source.shape[0:2], 2))
    image_source = image_source[
                   0 if pos_target_start[0] >= 0 else pos_target_start[0] * -1: image_source.shape[0],
                   0 if pos_target_start[1] >= 0 else pos_target_start[1] * -1: image_source.shape[1]
                   ]
    pos_target_start = [x if x >= 0 else 0 for x in pos_target_start]

    # calculate overlap bottom right and adjust
    pos_target_end = np.add(pos_target_start, image_source.shape[0:2])
    image_source = image_source[
                   0: image_source.shape[0]
                   if pos_target_end[0] < image_target.shape[0]
                   else image_source.shape[0] - (pos_target_end[0] - image_target.shape[0]),
                   0: image_source.shape[1]
                   if pos_target_end[1] < image_target.shape[1]
                   else image_source.shape[1] - (pos_target_end[1] - image_target.shape[1])
                   ]
    pos_target_end = [x if x <= image_target.shape[i] else image_target.shape[i] for i, x in enumerate(pos_target_end)]

    # paste image and deal with datatype min and max values (cut em off)
    image_return = (image_target.copy()).astype(image_source.dtype)
    image_return[pos_target_start[0]:pos_target_end[0], pos_target_start[1]:pos_target_end[1]] += image_source
    image_return[image_return > (np.iinfo(image_target.dtype)).max] = (np.iinfo(image_target.dtype)).max
    image_return[image_return < (np.iinfo(image_target.dtype)).min] = (np.iinfo(image_target.dtype)).min
    image_return = image_return.astype(image_target.dtype)

    return image_return


def beta_distribution(image_size, a=1.5, b=1.5):
    """Provides the beta 'discrete' probability distribution,
    used to initialize the random generator and to draw random values from.
    see https://en.wikipedia.org/wiki/Beta_distribution

    :param image_size: tuple of image dimensions
    :param a:
    :param b:
    :return: the beta continuous probability distribution as np matrix
    """

    normalize_const = (gamma(a) * gamma(b)) / gamma(a + b)

    horizontal = np.linspace(0, 1, image_size[0], dtype=np.float16)
    horizontal_distribution = np.array([(x ** (a - 1) * (1 - x) ** (b - 1)) / normalize_const
                                        for x in horizontal], dtype=np.float16)

    vertical = np.linspace(0, 1, image_size[1], dtype=np.float16)
    vertical_distribution = np.array([(x ** (a - 1) * (1 - x) ** (b - 1)) / normalize_const
                                      for x in vertical], dtype=np.float16)

    bdpd = np.outer(horizontal_distribution, vertical_distribution)  # same as transposing one and multiply with other
    bdpd[~np.isfinite(bdpd)] = 0  # for caution

    return bdpd


class Sampler:
    """Provides functionality for sampling random variables from a discrete finite 2d array.
    used to generate random x,y coordinates.
    see: https://stackoverflow.com/a/31675310
    """

    def __init__(self, dnf, seed=None):
        self.shape = dnf.shape  # save original shape of discrete probability density "function"
        dnf[~np.isfinite(dnf)] = 0  # compensate precision problems = hack
        self._cdf_flat = np.cumsum(dnf.astype(np.float))  # cumulative (1d) array of probability distribution
        self._cdf_flat = self._cdf_flat / self._cdf_flat.max()  # normalized cumulative distribution "function"
        self._rand = random.Random(seed)

    def rand2d(self):
        index = np.argmax(self._cdf_flat > self._rand.random())
        r = int(index / self.shape[1])
        c = (index - r * self.shape[1])
        return r, c
