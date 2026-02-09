

# SyncWatch

<p align="center">
  <img src="pictures/logo.svg" alt="SyncWatch Logo" width="200" height="200">
</p>

<p align="center"><b>Real-time volume sync monitor for Docker Swarm</b></p>

Displays sync status across all nodes with a live web dashboard. Detects discrepancies in replicated volumes instantly.

![demo](pictures/demo.gif)

## How it works

1. **Writer node** (lowest IP) writes a test file (`.consistency_test.json`) at a configurable interval (default 30s)
2. **All nodes** read the test file and report their view via API
3. **Dashboard** aggregates all nodes and shows sync status in real-time

## Requirement

- Initialized Docker Swarm (`docker swarm init`)

## Quick Start

Run only on **one node**

**!!! Please change `/var/syncthing/data` path in the `docker-compose.yml` to match your setup !!!**

```bash
# Clone the repository
git clone https://github.com/SuitDeer/SyncWatch.git
cd SyncWatch

# Deploy to Swarm
sudo docker stack deploy -c docker-compose.yml syncwatch
```

Open `http://<any-node-ip>:8081` in your browser to see dashboard.

## File Usage

| File                     | Purpose                                         |
| ------------------------ | ----------------------------------------------- |
| `.consistency_test.json` | Test file written by writer node                |
| `.syncwatch_config.json` | Shared configuration                            |

## Development

Run on **each node**:

```bash
# Clone the repository
git clone https://github.com/SuitDeer/SyncWatch.git
cd SyncWatch/dev

# Build image
sudo docker build -t syncwatch:local .
```

Run only on **one node**:

```bash
# Deploy to Swarm
sudo docker stack deploy -c docker-compose.yml syncwatch

sudo docker service logs syncwatch_syncwatch -f

sudo docker service logs syncwatch_dashboard -f

## Testing ...

sudo docker stack rm syncwatch
```

Run on **each node**:

```bash
# Remove dev image from local image repository
sudo docker image rm syncwatch:local
```
