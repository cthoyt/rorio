# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "click>=8.3.3",
#     "pyobo>=0.12.21",
# ]
# ///

import json
from pathlib import Path

import click

from pyobo.sources.ror import get_ror_to_country_geonames, RORGetter

HERE = Path(__file__).parent.resolve()
OFN_PATH = HERE.joinpath("rorio.ofn")
OBO_PATH = HERE.joinpath("rorio.obo")
OWL_PATH = HERE.joinpath("rorio.owl")
JSON_PATH = HERE.joinpath("rorio.json")
ROR_TO_COUNTRIES = HERE.joinpath("countries.json")


@click.command()
def main() -> None:
    ROR_TO_COUNTRIES.write_text(json.dumps(get_ror_to_country_geonames(), indent=2, sort_keys=True))

    ontology = RORGetter()
    ontology.write_obograph(JSON_PATH)
    ontology.write_owl(OWL_PATH)
    ontology.write_ofn(OFN_PATH)
    ontology.write_obo(OBO_PATH)
    # TODO synonyms?


if __name__ == "__main__":
    main()
