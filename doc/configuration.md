# MilleGrilles service instance configuration

## Disabled 3.protege required modules

On complex topologies, the core and mongo modules may be completely removed from the 3.protege instance. To ensure
they don't get restarted, create the file: /var/opt/millegrilles/configuration/disabled_modules.json.

Sample content: {"disabled": ["docker.core.json", "docker.mongo.json"]}.

