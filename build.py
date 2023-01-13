import datetime
import json
from pathlib import Path

import click
import pystow
from funowl import (
    Annotation,
    AnnotationAssertion,
    Class,
    ClassAssertion,
    NamedIndividual,
    ObjectProperty,
    ObjectPropertyAssertion,
    Ontology,
    OntologyDocument,
)
from rdflib import DC, DCTERMS, OWL, RDFS, Literal, Namespace, URIRef
from tqdm.auto import tqdm

# Paths and URLs
HERE = Path(__file__).parent.resolve()
OFN_PATH = HERE.joinpath("rorio.ofn")
DATA_URL = (
    "https://zenodo.org/record/7448410/files/v1.17.1-2022-12-16-ror-data.zip?download=1"
)
DATA_INNER_PATH = "v1.17.1-2022-12-16-ror-data.json"

# Namespaces
ORCID = Namespace("https://orcid.org/")
ROR = Namespace("https://ror.org/")
GEONAMES = Namespace("https://www.geonames.org/")
OBO = Namespace("http://purl.obolibrary.org/obo/")

# Constants
CITY_CLASS = OBO["ENVO_00000856"]
ORG_CLASS = OBO["OBI_0000245"]
LOCATED_IN = OBO["RO_0001025"]
CHARLIE = ORCID["0000-0003-4423-4370"]

ONTOLOGY_URI = "https://w3id.org/rorio/rorio.owl"
ONTOLOGY_URI_REF = URIRef(ONTOLOGY_URI)


def main():
    with pystow.ensure_open_zip(
        "ror", url=DATA_URL, inner_path=DATA_INNER_PATH
    ) as file:
        data = json.load(file)

    today = datetime.date.today().strftime("%Y-%m-%d")

    ontology = Ontology(iri=ONTOLOGY_URI_REF)
    ontology.annotations.extend(
        (
            Annotation(DC.title, "ROR in OWL"),
            Annotation(DC.creator, CHARLIE),
            Annotation(
                DCTERMS.license, "https://creativecommons.org/publicdomain/zero/1.0/"
            ),
            Annotation(RDFS.seeAlso, "https://github.com/cthoyt/rorio"),
            Annotation(OWL.versionInfo, today),
            Annotation(DC.source, DATA_URL),
        )
    )

    ontology.declarations(
        Class(CITY_CLASS), Class(ORG_CLASS), ObjectProperty(LOCATED_IN)
    )
    ontology.annotations.extend(
        [
            AnnotationAssertion(RDFS.label, CITY_CLASS, "city"),
            AnnotationAssertion(RDFS.label, ORG_CLASS, "organization"),
            AnnotationAssertion(RDFS.label, LOCATED_IN, "located in"),
        ]
    )

    for record in tqdm(data, unit_scale=True, unit="record"):
        organization_uri_ref = URIRef(record["id"])
        organization_name = record["name"]

        ontology.declarations(NamedIndividual(organization_uri_ref))
        try:
            ontology.annotations.extend(
                [
                    AnnotationAssertion(
                        RDFS.label,
                        organization_uri_ref,
                        Literal(organization_name),
                        # [Annotation(DC.source, URL)],
                    ),
                    ClassAssertion(ORG_CLASS, organization_uri_ref),
                ]
            )
        except (TypeError, AssertionError):
            tqdm.write(
                f"failed on organization: {organization_name} ({organization_uri_ref})"
            )
            continue

        for address in record.get("addresses", []):
            city = address.get("geonames_city")
            if not city:
                continue
            city_uri_ref = GEONAMES[str(city["id"])]
            city_name = city["city"]
            ontology.declarations(NamedIndividual(city_uri_ref))
            try:
                ontology.annotations.extend(
                    [
                        ObjectPropertyAssertion(
                            LOCATED_IN, organization_uri_ref, city_uri_ref
                        ),
                        AnnotationAssertion(
                            RDFS.label,
                            city_uri_ref,
                            Literal(city_name),
                            # [
                            #     Annotation(DC.source, URIRef("https://geonames.org/")),
                            #     Annotation(
                            #         DCTERMS.license, URIRef(city["license"]["license"])
                            #     ),
                            # ],
                        ),
                        ClassAssertion(CITY_CLASS, city_uri_ref),
                    ]
                )
            except AssertionError:
                tqdm.write(
                    f"[{organization_uri_ref}] failed on city: {city_name} ({city_uri_ref})"
                )
                continue

    doc = OntologyDocument(
        ontology=ontology,
        dc=DC,
        orcid=ORCID,
        obo=OBO,
        ror=ROR,
        dcterms=DCTERMS,
        owl=OWL,
        geonames=GEONAMES,
    )
    click.echo(f"writing to {OFN_PATH}")
    OFN_PATH.write_text(f"{doc}\n")


if __name__ == "__main__":
    main()
