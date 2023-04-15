# ROR in OWL

Similar to the [ORCIDIO](https://github.com/cthoyt/orcidio), which makes an ontology of instances of researchers via
ORCID, this repository houses a script to convert the [Research Organization Registry (ROR)](https://ror.org) into
an ontology of instances of organizations.

The latest version can be downloaded at https://w3id.org/rorio/rorio.owl. 

![](img/rorio-in-protege.png)

## Build

Install the requirements and run with:

```shell
python -m pip install -r requirements.txt
python build.py
```

## License

The data downloaded from https://doi.org/10.5281/zenodo.6347574 are licensed under CC0. So is this repo. This is
additionally self-documented in the ontology files.
