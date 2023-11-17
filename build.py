import json
import os
import zipfile
from pathlib import Path

import bioregistry
import click
import zenodo_client
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
from rdflib import DCTERMS, OWL, RDFS, Literal, Namespace, URIRef
from tqdm import tqdm
from gilda import Term
from gilda.term import dump_terms
from gilda.process import normalize

# Paths and URLs
HERE = Path(__file__).parent.resolve()
OFN_PATH = HERE.joinpath("rorio.ofn")
OWL_PATH = HERE.joinpath("rorio.owl")
JSON_PATH = HERE.joinpath("rorio.json")
GILDA_PATH = HERE.joinpath("rorio.gilda.tsv.gz")

# Namespaces
ORCID = Namespace("https://orcid.org/")
ROR = Namespace("https://ror.org/")
GEONAMES = Namespace("https://www.geonames.org/")
OBO = Namespace("http://purl.obolibrary.org/obo/")
BFO = Namespace("http://purl.obolibrary.org/obo/BFO_")
ENVO = Namespace("http://purl.obolibrary.org/obo/ENVO_")
OBI = Namespace("http://purl.obolibrary.org/obo/OBI_")
RO = Namespace("http://purl.obolibrary.org/obo/RO_")
OMO = Namespace("http://purl.obolibrary.org/obo/OMO_")
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
    "'s-Heerenberg": "s-Heerenberg",
    "Institut Virion\\Serion": "Institut Virion/Serion",
    "Hematology\\Oncology Clinic": "Hematology/Oncology Clinic",
}

ONTOLOGY_URI = "https://w3id.org/rorio/rorio.owl"

#: Zenodo ID for ROR
PERMENANT = "10086202"


def get_latest():
    client = zenodo_client.Zenodo()
    latest_record_id = client.get_latest_record(PERMENANT)
    response = client.get_record(latest_record_id)
    response_json = response.json()
    version = response_json["metadata"]["version"].lstrip("v")
    file_record = response_json["files"][0]
    name = file_record["key"]
    url = file_record["links"]["self"]
    path = client.download(latest_record_id, name=name)
    with zipfile.ZipFile(path) as zf:
        for zip_info in zf.filelist:
            if zip_info.filename.endswith(".json"):
                with zf.open(zip_info) as file:
                    return version, url, json.load(file)
    raise FileNotFoundError


@click.command()
@click.option("--quiet", is_flag=True)
def main(quiet: bool):
    version, source_uri, records = get_latest()
    unhandled_xref_prefixes = set()

    ontology = Ontology(iri=URIRef(ONTOLOGY_URI))
    ontology.annotations.extend(
        (
            Annotation(DCTERMS.title, "ROR in OWL"),
            Annotation(DCTERMS.creator, CHARLIE),
            Annotation(DCTERMS.license, "https://creativecommons.org/publicdomain/zero/1.0/"),
            Annotation(RDFS.seeAlso, "https://github.com/cthoyt/rorio"),
            Annotation(OWL.versionInfo, Literal(version)),
            Annotation(DCTERMS.source, URIRef(source_uri)),
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

    terms: list[Term] = []

    def _add_term(t, luid, entry_name, status):
        terms.append(
            Term(
                norm_text=normalize(t),
                text=t,
                db="ror",
                id=luid,
                entry_name=entry_name,
                status=status,
                source="ror",
            )
        )

    for record in tqdm(
        records,
        unit_scale=True,
        unit="record",
        desc=f"ROR v{version} to OWL",
        disable=quiet,
    ):
        organization_uri_ref = URIRef(record["id"])
        organization_luid = record["id"].removeprefix("https://ror.org/")
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
                    ),
                    ClassAssertion(ORG_CLASS, organization_uri_ref),
                ]
            )
        except (TypeError, AssertionError):
            tqdm.write(f"failed on organization: {organization_name} ({organization_uri_ref})")
            continue
        _add_term(organization_name, organization_luid, organization_name, "name")

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
                        ObjectPropertyAssertion(LOCATED_IN, organization_uri_ref, city_uri_ref),
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
                tqdm.write(f"[{organization_uri_ref}] failed on city: {city_name} ({city_uri_ref})")
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
            _add_term(synonym, organization_luid, organization_name, "synonym")

        for acronym in record.get("acronyms", []):
            try:
                ontology.annotations.append(
                    AnnotationAssertion(
                        OIO["hasExactSynonym"],
                        organization_uri_ref,
                        Literal(acronym),
                        [
                            Annotation(OIO["SynonymType"], OMO["0003000"]),
                        ],
                    )
                )
            except (AssertionError, TypeError):
                tqdm.write(
                    f"bad acronym for {organization_name} ({organization_uri_ref}): {acronym}"
                )
                continue
            # Acronyms cause collisions with country and city acronyms, skip for now
            # _add_term(acronym, organization_luid, organization_name, "synonym")

        for prefix, xref_data in record.get("external_ids", {}).items():
            if prefix == "OrgRef":
                # OrgRef refers to wikipedia page id, see
                # https://stackoverflow.com/questions/6168020/what-is-wikipedia-pageid-how-to-change-it-into-real-page-url
                continue
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
                        Literal(bioregistry.curie_to_str(norm_prefix, xref_id.replace(" ", ""))),
                    )
                )

    doc = OntologyDocument(
        ontology=ontology,
        orcid=ORCID,
        obo=OBO,
        ror=ROR,
        dcterms=DCTERMS._NS,
        owl=OWL._NS,
        geonames=GEONAMES,
        oio=OIO,
        BFO=BFO,
        RO=RO,
    )
    click.echo(f"writing to {OFN_PATH}")
    OFN_PATH.write_text(f"{doc}\n")

    # TODO add prefix file for conversion to shorten files
    cmd = f"robot convert --input {OFN_PATH} --output {OFN_PATH}"
    click.secho("Canonicalizing OFN")
    click.secho(cmd, fg="green")
    os.system(cmd)

    cmd = f"robot convert --input {OFN_PATH} --output {OWL_PATH}"
    click.secho(cmd, fg="green")
    os.system(cmd)

    cmd = f"robot convert --input {OFN_PATH} --output {JSON_PATH}"
    click.secho(cmd, fg="green")
    os.system(cmd)

    click.secho(f"writing Gilda index to {GILDA_PATH}", fg="green")
    dump_terms(terms, GILDA_PATH)


if __name__ == "__main__":
    main()
