#!/usr/bin/env python3
# encoding: utf-8

# This file is part of CycloneDX Conan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) OWASP Foundation. All Rights Reserved.

import argparse
import hashlib
import json
import os.path
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from conans.client.conan_api import Conan, ProfileData
from conans.client.command import Command as ConanCommand, OnceArgument, Extender, _add_common_install_arguments
from conans.client.graph.graph import DepsGraph, Node
from conans.client.output import ConanOutput, colorama_initialize
from conans.errors import ConanMigrationError, ConanException
from cyclonedx.factory.license import LicenseFactory
from cyclonedx.model.bom import Bom
from packageurl import PackageURL
from typing import Set


class CycloneDXCommand:
    # Parsed Arguments
    _arguments: argparse.Namespace

    def __init__(self, args: argparse.Namespace):
        self._arguments = args

    @staticmethod
    def get_arg_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description='CycloneDX SBOM Generator')

        parser.add_argument("path_or_reference", help="Path to a folder containing a recipe"
                                                      " (conanfile.py or conanfile.txt) or to a recipe file. e.g., "
                                                      "./my_project/conanfile.txt. It could also be a reference")
        parser.add_argument("-if", "--install-folder", action=OnceArgument,
                            help="local folder containing the conaninfo.txt and conanbuildinfo.txt "
                                 "files (from a previous conan install execution). Defaulted to "
                                 "current folder, unless --profile, -s or -o is specified. If you "
                                 "specify both install-folder and any setting/option "
                                 "it will raise an error.")
        dry_build_help = ("Apply the --build argument to output the information, "
                          "as it would be done by the install command")
        parser.add_argument("-db", "--dry-build", action=Extender, nargs="?", help=dry_build_help)
        output_help = 'Output file path for your SBOM (set to \'-\' to output to STDOUT)'
        parser.add_argument(
            '--output', action='store', metavar='FILE_PATH', default="-", required=False,
            help=output_help, dest='output_file'
        )
        exclude_dev_help = 'Exclude development dependencies from the BOM'
        parser.add_argument(
            '--exclude-dev', action='store_true',
            help=exclude_dev_help, dest='exclude_dev'
        )
        build_help = ("Given a build policy, return an ordered list of packages that would be built"
                      " from sources during the install command")

        update_help = "Will check if updates of the dependencies exist in the remotes " \
                      "(a new version that satisfies a version range, a new revision or a newer " \
                      "recipe if not using revisions)."
        _add_common_install_arguments(parser, update_help=update_help, build_help=build_help)

        return parser

    @staticmethod
    def generate_license(license_name):
        if not license_name:
            return None
        lf = LicenseFactory().make_from_string(license_name)
        if lf.id:
            return [{"license": {"id": lf.id}}]
        return [{"license": {"name": lf.name}}]

    @staticmethod
    def generate_hash(component, conan_api, node):
        lib_path = (Path(
            conan_api.cache_folder) / "data" / node.ref.name / node.ref.version / "_" / "_" /
                    "package" /
                    f"{node.graph_lock_node.package_id}" / "lib")
        if not lib_path.exists():
            return
        hash = hashlib.sha256()

        for file in lib_path.glob("*"):
            try:
                hash.update(file.read_bytes())
            except IsADirectoryError:
                pass
        component["hashes"] = [{"alg": "SHA-256", "content": hash.hexdigest()}]

    def execute(self):
        try:
            conan_api = Conan(output=ConanOutput(sys.stderr, sys.stderr, colorama_initialize()))
        except ConanMigrationError:  # Error migrating
            sys.exit(1)
        except ConanException as e:
            sys.stderr.write("Error in Conan initialization: {}".format(e))
            sys.exit(1)
        conan_command = ConanCommand(conan_api)

        profile_build = ProfileData(profiles=self._arguments.profile_build,
                                    settings=self._arguments.settings_build,
                                    options=self._arguments.options_build,
                                    env=self._arguments.env_build,
                                    conf=self._arguments.conf_build)
        data = conan_command._conan.info(
            self._arguments.path_or_reference,
            remote_name=self._arguments.remote,
            settings=self._arguments.settings_host,
            options=self._arguments.options_host,
            env=self._arguments.env_host,
            profile_names=self._arguments.profile_host,
            conf=self._arguments.conf_host,
            profile_build=profile_build,
            update=self._arguments.update,
            install_folder=self._arguments.install_folder,
            build=self._arguments.dry_build,
            lockfile=self._arguments.lockfile)

        deps_graph: DepsGraph = data[0]

        bom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.3",
            "serialNumber": "urn:uuid:" + str(uuid4()),
            "version": 1,
            'metadata': {
                'timestamp': f"{datetime.now(tz=timezone.utc).isoformat()}",
                'component': {
                    'bom-ref': 'unknown@0.0.0',
                    'type': 'application',
                    'name': 'unknown',
                    'version': '0.0.0',
                },
            },
            'components': [],
            'dependencies': [],
        }
        if deps_graph.root.conanfile.author:
            bom['metadata']["author"] = [{"name": deps_graph.root.conanfile.author}]
        required_ids = set()
        if self._arguments.exclude_dev:
            visited_ids = set()
            to_visit: Set[Node] = set(node for node in deps_graph.nodes if node.ref is None)
            while to_visit:
                node = to_visit.pop()
                if node.id in visited_ids:
                    continue
                visited_ids.add(node.id)
                required_ids.add(node.id)
                for dependency in node.dependencies:
                    if str(dependency.dst.id) in node.graph_lock_node.requires:
                        to_visit.add(dependency.dst)
        if deps_graph.root.ref:
           # bom['metadata']['component']['authors'] = [{"name": deps_graph.root.conanfile.author}]
            bom['metadata']['component']['name'] = deps_graph.root.ref.name
            bom['metadata']['component']['version'] = deps_graph.root.ref.version
            if deps_graph.root.conanfile.license:
                bom['metadata']['component']['licenses'] = CycloneDXCommand.generate_license(deps_graph.root.conanfile.license)
            bom['metadata']['component'][
                'bom-ref'] = f"{bom['metadata']['component']['name']}@{bom['metadata']['component']['version']}"
        for node in deps_graph.nodes:
            if node.ref is None:
                # top level component
                bom['metadata']['component']['name'] = os.path.basename(os.path.dirname(node.path))
                bom['metadata']['component']['bom-ref'] = bom['metadata']['component']['name'] + '@' + \
                                                          bom['metadata']['component']['version']
                dependencies = {
                    'ref': bom['metadata']['component']['bom-ref'],
                    'dependsOn': [],
                }
                for dependency in node.dependencies:
                    purl = get_purl(dependency.dst.remote, dependency.dst.ref)
                    if (
                            self._arguments.exclude_dev
                            and str(dependency.dst.id) not in required_ids
                    ):
                        continue
                    dependencies['dependsOn'].append(str(purl))
                bom['dependencies'].append(dependencies)
            else:

                if (
                        self._arguments.exclude_dev
                        and str(node.id) not in required_ids
                ):
                    continue
                purl = get_purl(node.remote, node.ref)
                component = {
                    'bom-ref': str(purl),
                    'type': 'library',
                    'name': node.ref.name,
                    'version': node.ref.version,
                    'purl': str(purl),
                }
                if deps_graph.root.conanfile.license:
                    component['licenses']= CycloneDXCommand.generate_license(deps_graph.root.conanfile.license)
                if node.graph_lock_node:
                    CycloneDXCommand.generate_hash(component, conan_api, node)
                if node.ref.user:
                    component['namespace'] = node.ref.user
                bom['components'].append(component)
                dependencies = {
                    'ref': component['bom-ref'],
                    'dependsOn': [],
                }
                for dependency in node.dependencies:
                    if (
                            self._arguments.exclude_dev
                            and str(dependency.dst.id) not in required_ids
                    ):
                        continue
                    dep_purl = get_purl(dependency.dst.remote, dependency.dst.ref)
                    dependencies['dependsOn'].append(str(dep_purl))
                bom['dependencies'].append(dependencies)

        output = json.dumps(bom, indent=2)
        if self._arguments.output_file == '-' or not self._arguments.output_file:
            print(output)
        else:
            with open(self._arguments.output_file, "w") as file:
                file.write(output)


def get_purl(remote, ref):
    qualifiers = {
        'repository_url': 'localhost' if remote is None else remote.url,
    }
    if ref.user:
        qualifiers['channel'] = ref.channel
    purl = PackageURL(type='conan', namespace=ref.user, name=ref.name, version=ref.version, qualifiers=qualifiers)
    return purl


def main():
    parser = CycloneDXCommand.get_arg_parser()
    args = parser.parse_args()
    CycloneDXCommand(args).execute()


if __name__ == '__main__':
    main()
