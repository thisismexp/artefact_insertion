# This script shows basic usage of the provided package

from src.repository import ArtefactsRepository
from src.types import *

if __name__ == "__main__":

    # define location of the meta.json file (describing the artefacts)
    meta = 'data/artefacts/meta.json'

    # obtain an instance of the Repository object which allows easy interaction with a collection of Artefact objects,
    # use seed to make initialization and selection deterministic (pseudo-random if seed=None)
    repo = ArtefactsRepository(meta, seed=None)

    # load an image and corresponding mask (see Credits in the README.md file)
    test_image = Image.open('data/test_images/ISIC_0024311.jpg')
    test_mask = Image.open('data/test_masks/ISIC_0024311.png')

    # get a random artefact
    a = repo.get_random_instance()

    # it returns one instance of a subclass of Artefact
    print(type(a))
    print(isinstance(a, Artefact))

    # this instance can be applied to any given image, even multiple times
    a(test_image, test_mask).show()
    a(test_image, test_mask).show()
    a(test_image, test_mask).show()

    # use an artefact of a specific type ...
    b = repo.get_random_instance(artefact_class=Bubble)
    print(type(b))

    # ... or one of several
    b = repo.get_random_instance(artefact_class=(RulerVertical, MarkingCircle))
    print(type(b))
