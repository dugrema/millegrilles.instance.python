import pathlib
import yaml


def load_yaml_recursive(yaml_file: pathlib.Path) -> dict:
    with open(yaml_file) as f:
        compose_configuration: dict = yaml.safe_load(f)

    try:
        include_files = compose_configuration['include']
        files_dict = dict()
        compose_configuration['x-include-content'] = files_dict
        for include_file in include_files:
            include_file_path = yaml_file.parent.joinpath(include_file).resolve()
            file_content = load_yaml_recursive(include_file_path)
            files_dict[include_file_path] = file_content
    except KeyError:
        pass

    return compose_configuration

def extract_certificate_list(configuration_file: dict):
    certificats_to_manage = []
    for key, value in configuration_file.items():
        try:
            services = value['services']
        except KeyError:
            continue

        for service_name, service_config in services.items():
            try:
                certificate_config = service_config['x-millegrilles-certificat'].copy()
                certificate_config['name'] = service_name
                certificats_to_manage.append(certificate_config)
            except KeyError:
                continue

    pass

def parse_compose_node(node_file: pathlib.Path):
    configuration_file = load_yaml_recursive(node_file)
    certificate_configuration_list = extract_certificate_list(configuration_file['x-include-content'])
    pass

def main():
    parse_compose_node(pathlib.Path("../etc/compose/middleware/node-protege.yml"))

if __name__ == "__main__":
    main()
