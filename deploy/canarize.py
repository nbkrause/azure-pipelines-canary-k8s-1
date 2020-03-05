#!/usr/bin/env python3

import argparse
import os.path
import copy
import sys
from os import path


# the suffix added to all the resources
DEFAULT_CANARY_SUFFIX = "-canary"

# default Prefix for the Mappings to the Service
DEFAULT_MAPPINGS_PREFIX = "/"

# hack for installing some package if it is not available


def install_and_import(importname, package):
    import importlib
    try:
        importlib.import_module(importname)
    except ImportError:
        import pip
        pip.main(['install', package])
    finally:
        return importlib.import_module(importname)


yaml = install_and_import("yaml", "pyyaml")


class StoreDictKeyPair(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        my_dict = {}
        for kv in values.split(","):
            k, v = kv.split("=")
            my_dict[k] = v
        setattr(namespace, self.dest, my_dict)


def image_tag(name):
    try:
        return name.split(":")[-1]
    except:
        return ""


def image_except_tag(name):
    try:
        ":".join(name.split(":")[:-1])
    except:
        return name


def image_replace_tag(name, new_tag):
    try:
        ":".join([image_except_tag(name), new_tag])
    except:
        return name


def gen_mapping(args, service, weight=None, labels={}):
    """
    Generate a Mapping for a service/prefix and (optional) weight
    """
    prefix = args.prefix
    mapping = {
        "apiVersion": "getambassador.io/v1",
        "kind":  "Mapping",
        "metadata": {
            "name":  f"mapping-for-{service}"
        },
        "spec": {
            "prefix": prefix,
            "service": service
        }
    }

    if args.namespace:
        mapping["metadata"]["namespace"] = args.namespace

    if len(labels) > 0:
        mapping["metadata"]["labels"] = labels

    if weight:
        mapping["spec"]["weigth"] = weight

    return mapping


def canarize_deployment(args, input_yaml, labels={}):
    """
    Create a canary for an existing Deployment.
    We do this by:
    - adding a '-canary' suffix to the name of the Deployment
    - adding a '-canary' suffix to all the labels in the Service selector
      as well as in the Pods template.
    """

    # append the -canary to the Deployment name
    output_yaml = copy.deepcopy(input_yaml)
    canary_deployment_name = input_yaml["metadata"]["name"] + args.suffix
    output_yaml["metadata"]["name"] = canary_deployment_name

    print(f"# Creating canary Deployment {canary_deployment_name}")

    # append the -canary to all the labels in the selector
    try:
        for (k, v) in input_yaml["spec"]["selector"]["matchLabels"].items():
            output_yaml["spec"]["selector"]["matchLabels"][k] = v + \
                args.suffix
    except IndexError:
        pass

    for (k, v) in input_yaml["spec"]["template"]["metadata"]["labels"].items():
        output_yaml["spec"]["template"]["metadata"]["labels"][k] = v + args.suffix

    if args.image:
        for container in output_yaml["spec"]["template"]["spec"]["containers"]:
            if image_except_tag(container["image"]) == image_except_tag(args.image):
                print(f"# Replacing Deployment image {args.image}")
                container["image"] = args.image

    if args.namespace:
        output_yaml["metadata"]["namespace"] = args.namespace

    if len(labels) > 0:
        if len(output_yaml["metadata"]["labels"]) > 0:
            output_yaml["metadata"]["labels"].update(labels)
        else:
            output_yaml["metadata"]["labels"] = labels

    return [output_yaml]


def canarize_service(args, input_yaml, labels={}):
    """
    Create a canary for an existing Service.
    We do this by:
    - adding a '-canary' suffix to the name of the Service
    - adding a '-canary' suffix to all the labels in the Service selector
    """
    res = []

    # append the -canary to the Service name
    output_yaml = copy.deepcopy(input_yaml)
    canary_service_name = input_yaml["metadata"]["name"] + args.suffix
    output_yaml["metadata"]["name"] = canary_service_name

    print(f"# Creating canary Service {canary_service_name}")

    # append the -canary to all the labels in the selector
    for (k, v) in input_yaml["spec"]["selector"].items():
        output_yaml["spec"]["selector"][k] = v + args.suffix

    if args.namespace:
        output_yaml["metadata"]["namespace"] = args.namespace

    res += [output_yaml]

    if args.gen_mapping:
        canary_service_name = output_yaml["metadata"]["name"]
        print(
            f"# Creating Mapping for Service {canary_service_name} (weight: {args.canary_weight})")
        res += [gen_mapping(args, canary_service_name,
                            weight=args.canary_weight, labels=labels)]

    if len(labels) > 0:
        if len(output_yaml["metadata"]["labels"]) > 0:
            output_yaml["metadata"]["labels"].update(labels)
        else:
            output_yaml["metadata"]["labels"] = labels

    return res


def canarize(args, input_yaml):
    """
    Create a canary for existing resources
    """
    if input_yaml["kind"] == "Deployment":
        return canarize_deployment(args, input_yaml, args.labels)
    elif input_yaml["kind"] == "Service":
        return canarize_service(args, input_yaml, args.labels)
    else:
        return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Canarize a set of files.")
    parser.add_argument("--suffix", "-s", default=DEFAULT_CANARY_SUFFIX,
                        help="suffix for the resources names")
    parser.add_argument("--prefix", "-P",
                        default=DEFAULT_MAPPINGS_PREFIX,
                        help="prefix for all the Mappings")
    parser.add_argument("--gen-mapping", "-m",
                        action="store_true",
                        default=False,
                        help="generate a Mapping only for the canary")
    parser.add_argument("--debug",
                        action="store_true",
                        default=False,
                        help="enable some debugging")
    parser.add_argument("--namespace", "-n",
                        default=None,
                        help="namespace")
    parser.add_argument("--image", "-I",
                        default=None,
                        help="image to use in the deployment")
    parser.add_argument("--canary-weight", "-w",
                        default=None,
                        type=int,
                        help="weight for the service")
    parser.add_argument("--output", "-o",
                        metavar="FILE", type=argparse.FileType('w'),
                        default=sys.stdout,
                        help="output file")
    parser.add_argument("--labels", "-l",
                        dest="labels",
                        action=StoreDictKeyPair,
                        metavar="KEY1=VAL1,KEY2=VAL2...",
                        help="extra labels for generated resources")
    parser.add_argument("files", metavar="FILE", type=argparse.FileType('r'),
                        default=sys.stdin, nargs='+', help="a manifest to process")

    args = parser.parse_args()

    if not args.suffix.startswith("-"):
        args.suffix = "-" + args.suffix

    res = []
    for f in args.files:
        for s in f.read().split("---"):
            if not s:
                continue

            try:
                in_yaml = yaml.safe_load(s)
                res += canarize(args, in_yaml)

            except yaml.YAMLError as exc:
                print(f"Error parsing manifest {f}:")
                print(exc)

    print(f"# Writting to {args.output.name}")
    res_str = "---\n" + "---\n".join([yaml.dump(x) for x in res])

    args.output.write(res_str)

    if args.debug and not ("stdout" in args.output.name):
        print(f"# File contents:")
        print(res_str)
