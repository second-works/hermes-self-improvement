"""Bind the OpenAI selection to the existing isolated registered-operation run."""
from pathlib import Path

from delegation.catalog import available_operations, registered_source_hashes
from delegation.openai_provider import Config, Provider
from delegation.registered import run
from evaluation.core import canonical, digest, load_json, regular, require, write_new


def run_openai(root, source_path, config_path, output_path, *, allow_api=False,
               execute=False, provider_factory=Provider, sandbox_factory=None):
    root = Path(root).resolve()
    config = Config.parse(load_json(regular(config_path, root, 8192)))
    require(allow_api is True, 'API_OPT_IN_REQUIRED')
    source = regular(source_path, root, 65536)
    baseline = regular(root / 'fixtures/delegation/registered-operations/review.py', root, 65536)
    require(digest(source) in registered_source_hashes(baseline), 'UNREGISTERED_SOURCE')
    output = Path(output_path).absolute()
    require(output.is_relative_to(root / 'runs') and '..' not in output.parts, 'RUN_BOUNDARY')
    for parent in (root / 'runs', *output.parents):
        if parent.is_relative_to(root / 'runs'):
            require(parent.is_dir() and not parent.is_symlink(), 'RUN_PARENT')
    output.mkdir(mode=0o700, exist_ok=False)
    provider = provider_factory(config, allow_api=allow_api)
    status = 'FAILED'
    try:
        selection = provider.select({'available_operations': available_operations(source.decode())})
        # Persist only the normalized allowlisted instruction, never the API envelope.
        selection_path = output / 'selection.json'
        write_new(selection_path, canonical(selection) + b'\n')
        require(regular(source_path, root, 65536) == source, 'SOURCE_CHANGED')
        report = run(root, source_path, selection_path, output / 'candidate',
                     execute=execute, sandbox_factory=sandbox_factory)
        # The existing candidate report describes the supplied selection file;
        # the outer report records provider provenance without changing that contract.
        status = report['status']
        return {'status': status, 'provider': provider.metadata(), 'candidate': report}
    finally:
        write_new(output / 'provider-report.json', canonical({
            'schema_version': 1, 'status': status, 'classification': 'PUBLIC',
            'source_sha256': digest(source), 'provider': provider.metadata()}) + b'\n')
