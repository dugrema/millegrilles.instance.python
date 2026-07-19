# Application Management Design

This document outlines the design for the application lifecycle management within the MilleGrilles instance.

## Overview

The application management system provides a robust way to install, uninstall, and list web applications. It supports various application types (static files, Nginx proxies, or Docker Compose services) and maintains a centralized catalogue of installed applications and a remote catalogue of available applications.

## 1. Application Package Format (`.tar.gz`)

Applications are distributed as compressed `.tar.gz` files. The contents are flexible to support different types of applications.

### Package Components

| Component | File/Directory       | Requirement | Description                                           |
| :--- |:---------------------| :--- |:------------------------------------------------------|
| **Metadata** | `metadata.json`      | **Required** | Contains application identity and localization.       |
| **Docker Compose** | `docker-compose.yml` | Optional | Docker Compose configuration for the application.     |
| **Nginx Config** | `nginx/`             | Optional | Nginx server configuration files for the application. |
| **Application Files** | `files/`             | Optional | Static files to be served via Nginx.                  |

### Detailed Component Specifications

#### `metadata.json`
Used to register the application in the local catalogue and provide human-readable names.
```json
{
  "name": "app_name",
  "version": "major.minor.build",
  "labels": {
    "en": "English Name",
    "fr": "Nom Français"
  },
  "path": "app_path",
  "portal": {
    "path": "https://a_custom.url/with/a/path",
    "port": 8000,
    "admin": false
  }
}
```
- `name`: A unique identifier for the application.
- `version`: The version of this application file.
- `labels`: A dictionary of localized names to display for this application.
- `path`: Optional - The relative subdirectory name used under `${MILLEGRILLES_ROOT}/var/nginx/html/applications/`, required only when `files/` are present.
- `portal`: Optional - Parameters used to display a web link on the user's portal. When present (event if empty), a web link is displayed to the user.
- `path`: Optional - Either a relative path or complete url (with https://...) that is supplied to the front-end for the link on the user's portal. Default is application path.
- `port`: Optional - Tells the web application the link is on the same hostname but different port.
- `admin`: Optional - When true, only administrators see the link.

#### `nginx/`
If present, contains files to be placed directly in `${MILLEGRILLES_ROOT}/etc/nginx/applications/`.

#### `docker-compose.yml`
If present, this file is renamed to `${app_name}.yml` and placed in `${MILLEGRILLES_ROOT}/etc/compose/applications/`. It is also added to the `include` list in `${MILLEGRILLES_ROOT}/etc/compose/applications.yml`.

#### `files/`
If this directory is present, its contents are extracted to `${MILLEGRILLES_ROOT}/var/nginx/html/applications/{path}`.

---

## 2. Catalogue Management

### Remote Catalogue (Discovery)
A centralized web server hosts remote catalogues for different environments (`dev`, `test`, `stable`).
- **URL Format**: `https://libs.millegrilles.com/archives/{env}.json`
- **Entry Structure**:
  ```json
  {
    "app_name": {
      "url": "https://libs.millegrilles.com/archives/app_name.2026.1.2.tar.gz",
      "version": "2026.1.2",
      "sha256": "abcdef123456...",
      "labels": {
        "en": "English Name",
        "fr": "Nom Français"
      }
    }
  }
  ```

### Local Installed Catalogue
The local instance maintains a record of all installed applications.
- **Location**: `${MILLEGRILLES_ROOT}/etc/installed_applications.json`
- **Entry Structure**:
  ```json
  {
    "app_name": {
      "version": "major.minor.build",
      "path": "app_path",
      "labels": {
        "en": "English Name",
        "fr": "Nom Français"
      },
      "portal": {
        "path": "https://a_custom.url/with/a/path",
        "admin": false
      }
    }
  }
  ```

---

## 3. Management Tools

### `bin/install/manage_apps.py` (The Orchestrator)
The primary Python-based CLI for managing applications. It encapsulates all logic for discovery, installation, and uninstallation.

**Commands:**

- **`install [--name <name> [--version <version>] [--env <dev|test|stable>] [--catalogue_url <url>]] | [--url <url> [--hash <hash>]] [--root <path>]`**
  - Resolves application details via the remote catalogue if `--name` is used (defaults to `https://libs.millegrilles.com/archives/stable.json`).
  - Downloads and verifies the package.
  - Configures Nginx, Docker Compose (`applications.yml` include list), and Application files.
  - Updates the local `installed_applications.json`.
  - Restarts the Nginx service.

- **`uninstall --name <name> --root <path>`**
  - Removes application files, Nginx configs, and Docker Compose files.
  - Updates the `applications.yml` include list.
  - Removes the application from `installed_applications.json`.
  - Restarts the Nginx service.

- **`list [--env <dev|test|stable>] | [--catalogue_url <url>] `**
  - Fetches and displays available applications from the remote catalogue.

- **`list-installed --root <path>`**
  - Displays all applications currently installed on the local instance.

### `bin/install/install_webapp.sh` (Low-Level Utility)
A lightweight Bash script focused strictly on downloading, extracting, and verifying a `.tar.gz` file. It does not handle orchestration or catalogue management.

### `apps.sh` (Developer Entry Point)
A root-level convenience script that:
1. Sets up the environment (`MILLEGRILLES_ROOT`, `config.env`).
2. Activates the Python virtual environment.
3. Provides a `manage-apps` command to interact with `manage_apps.py`.

---

## 4. Integration and Lifecycle

### Nginx Integration
To support the new application configuration structure, the main Nginx configuration must include the applications directory:
```nginx
# In regular https includes
include /etc/nginx/applications/*.location;

# In client TLS includes
include /etc/nginx/applications/*.location.tls;

# In server includes
include /etc/nginx/applications/*.server;
```

### Service Lifecycle
All installation and uninstallation actions trigger a **RELOAD** (not restart) of the Nginx service:
`systemctl --user reload ${INSTANCE_NAME}-nginx`
