#!/usr/bin/env python3
"""
SyncWatch - Volume sync monitor for Docker Swarm.
Build on each node, deploy as global service.
Auto-discovers peers via Docker Swarm DNS.
"""

import os
import json
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, jsonify, Response

app = Flask(__name__)


def get_my_ip():
    """Get container IP address."""
    try:
        return socket.gethostbyname(socket.gethostname())
    except:
        return "127.0.0.1"


# Config
DATA_PATH = os.environ.get("DATA_PATH", "/data")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "syncwatch")
DASHBOARD_MODE = os.environ.get("DASHBOARD_MODE", "false").lower() == "true"
HOSTNAME = socket.gethostname()
MY_IP = get_my_ip()
TEST_FILE = os.path.join(DATA_PATH, ".consistency_test.json")


def discover_peers():
    """Discover all checker containers via Docker Swarm DNS."""
    peers = []
    try:
        ips = socket.getaddrinfo(f"tasks.{SERVICE_NAME}", 8080, socket.AF_INET)
        for info in ips:
            ip = info[4][0]
            peers.append(ip)
    except socket.gaierror:
        pass
    return list(set(peers))


def discover_other_peers():
    """Discover other containers (excluding self)."""
    return [ip for ip in discover_peers() if ip != MY_IP]

# State
last_check = None
test_file_info = {}
check_interval = int(os.environ.get("CHECK_INTERVAL", "30"))
CONFIG_FILE = os.path.join(DATA_PATH, ".syncwatch_config.json")


def read_config():
    """Read config from shared file."""
    global check_interval
    try:
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
            check_interval = cfg.get("check_interval", check_interval)
    except:
        pass
    return {"check_interval": check_interval}


def write_config(cfg):
    """Write config to shared file."""
    global check_interval
    check_interval = cfg.get("check_interval", check_interval)
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump({"check_interval": check_interval}, f)
    except:
        pass


def write_test_file():
    """Write a test file with current timestamp for replication testing."""
    global test_file_info
    try:
        now = datetime.utcnow()
        data = {
            "written_by": HOSTNAME,
            "written_at": now.isoformat(),
            "timestamp": now.timestamp(),
            "sequence": test_file_info.get("sequence", 0) + 1
        }
        with open(TEST_FILE, "w") as f:
            json.dump(data, f)
        test_file_info = data
        return data
    except Exception as e:
        return {"error": str(e)}


def read_test_file():
    """Read the test file to check replication."""
    try:
        with open(TEST_FILE, "r") as f:
            return json.load(f)
    except:
        return None


def check_loop():
    """Background loop for checker nodes - writes test file if writer."""
    while True:
        read_config()  # Refresh interval from shared config
        peers = discover_other_peers()
        all_ips = sorted([MY_IP] + peers)
        is_writer = (all_ips[0] == MY_IP) if all_ips else True
        
        if is_writer:
            write_test_file()
        
        time.sleep(check_interval)


def dashboard_loop():
    """Background loop for dashboard - collects data from all checker nodes."""
    global last_check
    
    while True:
        all_checkers = discover_peers()
        
        result = {"all_nodes": []}
        
        for checker_ip in all_checkers:
            try:
                r = requests.get(f"http://{checker_ip}:8080/api/node_info", timeout=5)
                result["all_nodes"].append(r.json())
            except:
                result["all_nodes"].append({"ip": checker_ip, "error": "unreachable"})
        
        last_check = result
        time.sleep(0.5)


@app.route("/")
def index():
    """Dashboard showing test file content from each node."""
    html = """<!DOCTYPE html>
<html>
<head>
    <title>SyncWatch</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><polygon points='50,10 90,30 50,50 10,30' fill='%2316213e' stroke='%234caf50' stroke-width='2'/><circle cx='50' cy='30' r='4' fill='%234caf50'/><polygon points='50,30 90,50 50,70 10,50' fill='%2316213e' stroke='%234caf50' stroke-width='2'/><circle cx='50' cy='50' r='4' fill='%234caf50'/><polygon points='50,50 90,70 50,90 10,70' fill='%2316213e' stroke='%23f44336' stroke-width='3'/><circle cx='50' cy='70' r='4' fill='%23f44336'/></svg>">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"></script>
    <style>
        body { font-family: monospace; background: #1a1a2e; color: #eee; padding: 20px; margin: 0; overflow: hidden; }
        h1 { text-align: center; display: flex; align-items: center; justify-content: center; gap: 15px; }
        .logo { width: 50px; height: 50px; }
        .chart-container { background: #16213e; padding: 20px; border-radius: 8px; margin: 20px 0; }
        .chart-container h2 { margin: 0 0 15px 0; font-size: 14px; color: #888; text-align: center; }
        #syncChart { max-height: 300px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; margin: 20px 0; }
        .node { background: #16213e; padding: 15px; border-radius: 8px; transition: box-shadow 0.3s; }
        .node.changed { box-shadow: 0 0 15px #4caf50; }
        .node.synced { border-left: 4px solid #4caf50; }
        .node.out-of-sync { border-left: 4px solid #f44336; }
        .node h3 { margin: 0 0 10px 0; color: #4caf50; display: flex; justify-content: space-between; align-items: center; }
        .node.err h3 { color: #f44336; }
        .badge { font-size: 10px; background: #0d7377; padding: 2px 8px; border-radius: 10px; color: #fff; }
        .badge.sync { background: #4caf50; }
        .badge.desync { background: #f44336; }
        pre { background: #0d1117; padding: 10px; border-radius: 5px; overflow-x: auto; margin: 0; font-size: 13px; }
        .controls { text-align: center; margin: 20px 0; padding: 15px; background: #16213e; border-radius: 8px; }
        .controls label { margin-right: 10px; }
        .controls input { width: 60px; padding: 5px; border-radius: 4px; border: 1px solid #444; background: #0d1117; color: #eee; }
        .controls button { padding: 5px 15px; border-radius: 4px; border: none; background: #0d7377; color: #fff; cursor: pointer; margin-left: 10px; }
        .controls button:hover { background: #4caf50; }
        .controls .status { margin-left: 15px; font-size: 12px; color: #888; }
    </style>
</head>
<body>
    <h1>
        <svg class="logo" viewBox="0 0 100 100"><polygon points="50,10 90,30 50,50 10,30" fill="#16213e" stroke="#4caf50" stroke-width="2"/><circle cx="50" cy="30" r="4" fill="#4caf50"/><polygon points="50,30 90,50 50,70 10,50" fill="#16213e" stroke="#4caf50" stroke-width="2"/><circle cx="50" cy="50" r="4" fill="#4caf50"/><polygon points="50,50 90,70 50,90 10,70" fill="#16213e" stroke="#f44336" stroke-width="3"/><circle cx="50" cy="70" r="4" fill="#f44336"/></svg>
        SyncWatch
    </h1>
    <div class="controls">
        <label>Write Interval:</label>
        <input type="number" id="interval" min="1" max="3600" value="30">s
        <button onclick="updateInterval()">Update</button>
        <span id="configStatus" class="status"></span>
    </div>
    <div class="chart-container">
        <h2>Sync Delay by Sequence (ms)</h2>
        <canvas id="syncChart"></canvas>
    </div>
    <div id="content">Loading...</div>
    <script>
        let prevData = {};
        let latestNodes = null;
        let unsyncStart = {};  // Track when each node became unsynced
        let syncDelayHistory = {};  // { nodeName: { seq: delayMs } }
        let knownSequences = [];  // Ordered list of sequences
        let lastRecordedSeq = {};  // Track last recorded sequence per node
        let nodeColors = {};  // Persistent colors for nodes
        const MAX_SEQUENCES = 30;
        
        // Color palette for nodes
        const colorPalette = [
            '#f44336', '#e91e63', '#9c27b0', '#673ab7', '#3f51b5',
            '#2196f3', '#03a9f4', '#00bcd4', '#009688', '#ff9800',
            '#ff5722', '#795548', '#607d8b', '#8bc34a', '#cddc39'
        ];
        let colorIndex = 0;
        
        function getNodeColor(nodeName) {
            if (!nodeColors[nodeName]) {
                nodeColors[nodeName] = colorPalette[colorIndex % colorPalette.length];
                colorIndex++;
            }
            return nodeColors[nodeName];
        }
        
        // Initialize Chart.js
        const ctx = document.getElementById('syncChart').getContext('2d');
        const syncChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: []
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        labels: { color: '#eee', font: { family: 'monospace' } }
                    }
                },
                scales: {
                    x: {
                        title: { display: true, text: 'Sequence', color: '#888' },
                        ticks: { color: '#888' },
                        grid: { color: '#333' }
                    },
                    y: {
                        title: { display: true, text: 'Delay (ms)', color: '#888' },
                        ticks: { color: '#888' },
                        grid: { color: '#333' },
                        beginAtZero: true
                    }
                }
            }
        });
        
        function updateChart() {
            // Build labels from known sequences
            syncChart.data.labels = knownSequences.slice(-MAX_SEQUENCES);
            
            // Build datasets for each node (excluding writer)
            const datasets = [];
            for (const nodeName in syncDelayHistory) {
                const nodeData = syncDelayHistory[nodeName];
                const data = syncChart.data.labels.map(seq => nodeData[seq] !== undefined ? nodeData[seq] : null);
                
                datasets.push({
                    label: nodeName,
                    data: data,
                    borderColor: getNodeColor(nodeName),
                    backgroundColor: getNodeColor(nodeName) + '33',
                    tension: 0.3,
                    fill: false,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    spanGaps: true
                });
            }
            
            syncChart.data.datasets = datasets;
            syncChart.update('none');
        }
        
        // Load current config
        fetch('/api/config').then(r => r.json()).then(cfg => {
            document.getElementById('interval').value = cfg.check_interval || 30;
        });
        
        function updateInterval() {
            const val = parseInt(document.getElementById('interval').value);
            fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({check_interval: val})
            }).then(r => r.json()).then(d => {
                document.getElementById('configStatus').textContent = d.status === 'ok' ? '✓ Updated' : '✗ Error';
                setTimeout(() => document.getElementById('configStatus').textContent = '', 3000);
            });
        }
        
        function render() {
            if (!latestNodes || !latestNodes.length) {
                document.getElementById('content').innerHTML = '<p>Waiting for nodes...</p>';
                return;
            }
            
            const nodes = latestNodes;
            const writer = nodes.find(n => n.is_writer);
            const writerSeq = writer && writer.test_file ? writer.test_file.sequence : null;
            const now = Date.now();
            
            let html = '<div class="grid">';
            nodes.forEach(n => {
                const err = !!n.error;
                const key = n.hostname || n.ip;
                const curr = JSON.stringify(n.test_file, null, 2);
                const changed = prevData[key] && prevData[key] !== curr;
                
                const nodeSeq = n.test_file ? n.test_file.sequence : null;
                const synced = writerSeq !== null && nodeSeq === writerSeq;
                
                // Track unsync start time
                if (synced || n.is_writer) {
                    delete unsyncStart[key];
                } else if (!unsyncStart[key]) {
                    unsyncStart[key] = now;
                }
                
                const elapsedMs = unsyncStart[key] ? (now - unsyncStart[key]) : 0;
                const syncClass = n.is_writer ? '' : (synced ? ' synced' : ' out-of-sync');
                const syncBadge = n.is_writer ? '' : (synced ? '<span class="badge sync">SYNCED</span>' : '<span class="badge desync">+' + elapsedMs + 'ms</span>');
                
                html += '<div class="node' + (err ? ' err' : '') + (changed ? ' changed' : '') + syncClass + '">';
                html += '<h3><span>' + key + '</span><span>' + (n.is_writer ? '<span class="badge">WRITER</span>' : syncBadge) + '</span></h3>';

                if (latestNodes < 2 || latestNodes.length < 2) {
                    html += '<h4>Waiting for other nodes...</h4>';
                }

                html += '<pre>' + (err ? 'Unreachable' : curr) + '</pre>';
                html += '</div>';
            });
            html += '</div>';
            document.getElementById('content').innerHTML = html;
        }
        
        function fetchData() {
            fetch('/api/status').then(r => r.json()).then(d => {
                if (!d.all_nodes || !d.all_nodes.length) {
                    latestNodes = null;
                    return;
                }
                const nodes = d.all_nodes.slice().sort((a, b) => (a.hostname || a.ip).localeCompare(b.hostname || b.ip));
                
                // Find writer and current sequence
                const writer = nodes.find(n => n.is_writer);
                const writerSeq = writer && writer.test_file ? writer.test_file.sequence : null;
                const now = Date.now();
                
                // Track sync delays for chart
                if (writerSeq !== null) {
                    // Add sequence to known list if new
                    if (!knownSequences.includes(writerSeq)) {
                        knownSequences.push(writerSeq);
                        // Limit to MAX_SEQUENCES
                        if (knownSequences.length > MAX_SEQUENCES) {
                            const removed = knownSequences.shift();
                            // Clean up old data
                            for (const nodeName in syncDelayHistory) {
                                delete syncDelayHistory[nodeName][removed];
                            }
                        }
                    }
                    
                    // Record sync delays for non-writer nodes
                    nodes.forEach(n => {
                        if (n.is_writer || n.error) return;
                        
                        const key = n.hostname || n.ip;
                        const nodeSeq = n.test_file ? n.test_file.sequence : null;
                        
                        // Initialize history for this node
                        if (!syncDelayHistory[key]) {
                            syncDelayHistory[key] = {};
                        }
                        
                        // When node syncs to current sequence, record the delay
                        if (nodeSeq === writerSeq) {
                            // Only record if we haven't already recorded this sequence for this node
                            if (lastRecordedSeq[key] !== writerSeq) {
                                const delay = unsyncStart[key] ? (now - unsyncStart[key]) : 0;
                                syncDelayHistory[key][writerSeq] = delay;
                                lastRecordedSeq[key] = writerSeq;
                            }
                        }
                    });
                    
                    updateChart();
                }
                
                // Update prevData for change detection
                nodes.forEach(n => {
                    const key = n.hostname || n.ip;
                    prevData[key] = JSON.stringify(n.test_file, null, 2);
                });
                
                latestNodes = nodes;
            }).catch(e => {
                document.getElementById('content').innerHTML = '<p style="color:red">Error: ' + e + '</p>';
            });
        }
        
        fetchData();
        setInterval(fetchData, 500);
        
        render();
        setInterval(render, 50);
    </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")


@app.route("/api/node_info")
def api_node_info():
    """Return this node's test file content."""
    peers = discover_other_peers()
    all_ips = sorted([MY_IP] + peers)
    is_writer = (all_ips[0] == MY_IP) if all_ips else False
    is_writer = is_writer and not DASHBOARD_MODE
    
    return jsonify({
        "hostname": HOSTNAME,
        "ip": MY_IP,
        "test_file": read_test_file(),
        "is_writer": is_writer,
        "check_interval": check_interval
    })


@app.route("/api/config", methods=["GET"])
def api_get_config():
    """Get current config."""
    return jsonify(read_config())


@app.route("/api/config", methods=["POST"])
def api_set_config():
    """Update config (broadcasts to all nodes via shared file)."""
    from flask import request
    data = request.get_json() or {}
    if "check_interval" in data:
        try:
            interval = int(data["check_interval"])
            if interval >= 1:
                write_config({"check_interval": interval})
                return jsonify({"status": "ok", "check_interval": interval})
        except:
            pass
    return jsonify({"status": "error", "message": "Invalid interval"}), 400


@app.route("/api/status")
def api_status():
    """Return collected node data."""
    return jsonify(last_check or {"all_nodes": []})


# Start background loop at import time so it runs under Gunicorn too
if DASHBOARD_MODE:
    _bg = threading.Thread(target=dashboard_loop, daemon=True)
else:
    _bg = threading.Thread(target=check_loop, daemon=True)
_bg.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
