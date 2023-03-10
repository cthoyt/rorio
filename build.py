import datetime
import json
from pathlib import Path

import bioregistry
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
BFO = Namespace("http://purl.obolibrary.org/obo/BFO_")
ENVO = Namespace("http://purl.obolibrary.org/obo/ENVO_")
OBI = Namespace("http://purl.obolibrary.org/obo/OBI_")
RO = Namespace("http://purl.obolibrary.org/obo/RO_")
OIO = Namespace("http://www.geneontology.org/formats/oboInOwl#")

# Constants
CITY_CLASS = ENVO["00000856"]
ORG_CLASS = OBI["0000245"]
LOCATED_IN = RO["0001025"]
PART_OF = BFO["0000050"]
HAS_PART = BFO["0000051"]
SUCCESSOR = BFO["0000063"]
PREDECESSOR = BFO["0000062"]
CHARLIE = ORCID["0000-0003-4423-4370"]
RMAP = {
    "Related": RDFS.seeAlso,
    "Child": HAS_PART,
    "Parent": PART_OF,
    "Predecessor": PREDECESSOR,
    "Successor": SUCCESSOR,
}
NAME_REMAPPING = {
    "'s-Hertogenbosch": "Den Bosch",  # SMH Netherlands, why u gotta be like this
    "'s Heeren Loo": "s Heeren Loo",
    "Institut Virion\\Serion": "Institut Virion/Serion",
    "Hematology\\Oncology Clinic": "Hematology/Oncology Clinic",
}

# TODO handle prefxies HESA, UCAS, UKPRN, CNRS, and OrgRef
# OrgRef refers to wikipedia page id, see
# https://stackoverflow.com/questions/6168020/what-is-wikipedia-pageid-how-to-change-it-into-real-page-url

ONTOLOGY_URI = "https://w3id.org/rorio/rorio.owl"


def main():
    with pystow.ensure_open_zip(
        "ror", url=DATA_URL, inner_path=DATA_INNER_PATH
    ) as file:
        data = json.load(file)

    today = datetime.date.today().strftime("%Y-%m-%d")
    unhandled_xref_prefixes = set()

    ontology = Ontology(iri=URIRef(ONTOLOGY_URI))
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
        Class(CITY_CLASS),
        Class(ORG_CLASS),
        ObjectProperty(LOCATED_IN),
        *(ObjectProperty(p) for p in RMAP.values()),
    )
    ontology.annotations.extend(
        [
            AnnotationAssertion(RDFS.label, CITY_CLASS, "city"),
            AnnotationAssertion(RDFS.label, ORG_CLASS, "organization"),
            AnnotationAssertion(RDFS.label, LOCATED_IN, "located in"),
            AnnotationAssertion(RDFS.label, PART_OF, "part of"),
            AnnotationAssertion(RDFS.label, HAS_PART, "has part"),
            AnnotationAssertion(RDFS.label, SUCCESSOR, "precedes"),
            AnnotationAssertion(RDFS.label, PREDECESSOR, "preceded by"),
            AnnotationAssertion(RDFS.label, RDFS.seeAlso, "see also"),
        ]
    )

    for record in tqdm(data, unit_scale=True, unit="record"):
        organization_uri_ref = URIRef(record["id"])
        organization_name = record["name"]
        organization_name = NAME_REMAPPING.get(organization_name, organization_name)

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
            city_name = NAME_REMAPPING.get(city_name, city_name)
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

        for relationship in record.get("relationships", []):
            ontology.annotations.append(
                AnnotationAssertion(
                    RMAP[relationship["type"]],
                    organization_uri_ref,
                    URIRef(relationship["id"]),
                )
            )

        for synonym in record.get("aliases", []):
            try:
                ontology.annotations.append(
                    AnnotationAssertion(
                        OIO["hasExactSynonym"], organization_uri_ref, Literal(synonym)
                    )
                )
            except (AssertionError, TypeError):
                tqdm.write(
                    f"bad synonym for {organization_name} ({organization_uri_ref}): {synonym}"
                )
                continue

        for acronym in record.get("acronyms", []):
            try:
                # TODO add synonym type annotation?
                ontology.annotations.append(
                    AnnotationAssertion(
                        OIO["hasExactSynonym"], organization_uri_ref, Literal(acronym)
                    )
                )
            except (AssertionError, TypeError):
                tqdm.write(
                    f"bad acronym for {organization_name} ({organization_uri_ref}): {acronym}"
                )
                continue

        for prefix, xref_data in record.get("external_ids", {}).items():
            norm_prefix = bioregistry.normalize_prefix(prefix)
            if norm_prefix is None:
                if prefix not in unhandled_xref_prefixes:
                    tqdm.write(
                        f"Unhandled prefix: {prefix} in {organization_name} ({organization_uri_ref}). Values:"
                    )
                    for xref_id in xref_data["all"]:
                        tqdm.write(f"- {xref_id}")
                    unhandled_xref_prefixes.add(prefix)
                continue

            identifiers = xref_data["all"]
            if isinstance(identifiers, str):
                identifiers = [identifiers]
            for xref_id in identifiers:
                ontology.annotations.append(
                    AnnotationAssertion(
                        OIO["hasDbXref"],
                        organization_uri_ref,
                        Literal(
                            bioregistry.curie_to_str(
                                norm_prefix, xref_id.replace(" ", "")
                            )
                        ),
                    )
                )

    doc = OntologyDocument(
        ontology=ontology,
        dc=DC,
        orcid=ORCID,
        # obo=OBO,
        ror=ROR,
        dcterms=DCTERMS,
        owl=OWL,
        geonames=GEONAMES,
        oio=OIO,
        BFO=BFO,
        RO=RO,
        OBI=OBI,
        ENVO=ENVO,
    )
    click.echo(f"writing to {OFN_PATH}")
    OFN_PATH.write_text(f"{doc}\n")


if __name__ == "__main__":
    main()
