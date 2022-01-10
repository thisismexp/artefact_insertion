import json
import random
from os import path
from src.types import Artefact, Bubble, Marking, Ruler


class ArtefactsRepository:
    """Manages loading and handling of artefacts. """

    def __init__(self, meta_path, seed=None):

        self.artefacts = []
        self._rand = random.Random(seed)
        with open(meta_path) as meta_file:
            data = json.load(meta_file)
            for i, entry in enumerate(data['artefacts']):
                self.artefacts.append(Artefact(entry, path.dirname(meta_path), i + seed if seed else None))

    def get_random_instance(self, artefact_class=None):
        """
            returns one of the artefact objects randomly, or randomly within given classes
            :param artefact_class:
            :return: artefact object
        """
        if artefact_class is None:
            artefact_class = self._rand.choice([Bubble, Marking, Ruler])

        candidates = [item for item in self.artefacts if isinstance(item, artefact_class)]
        selected = self._rand.choice(candidates)
        return selected
