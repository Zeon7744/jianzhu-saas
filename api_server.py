"""
jianzhu-saas: Building Inspection SaaS API Server
"""
import os
import json
import hashlib
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
import re

class InspectionStore:
    """Simple in-memory store for building inspections."""
    
    def __init__(self):
        self.inspections = {}
        self.assessments = {}
    
    def create_inspection(self, data):
        inspection_id = str(uuid.uuid4())[:8]
        record = {
            'id': inspection_id,
            'created': time.time(),
            'status': 'pending',
            'data': data
        }
        self.inspections[inspection_id] = record
        return record
    
    def get_inspection(self, inspection_id):
        return self.inspections.get(inspection_id)
    
    def create_assessment(self, data):
        assessment_id = str(uuid.uuid4())[:8]
        
        # MLP-inspired risk scoring
        metrics = data.get('metrics', {})
        risk_score = self._calculate_risk(metrics)
        
        record = {
            'id': assessment_id,
            'created': time.time(),
            'risk_score': risk_score,
            'risk_level': self._risk_level(risk_score),
            'recommendations': self._recommendations(metrics, risk_score),
            'data': data
        }
        self.assessments[assessment_id] = record
        return record
    
    def _calculate_risk(self, m):
        """Calculate structural risk score (0-100, higher = more risk)."""
        score = 0.0
        # Concrete strength (MPa) - lower is worse
        cs = float(m.get('concrete_strength_mpa', 25))
        if cs < 15: score += 40
        elif cs < 20: score += 25
        elif cs < 25: score += 10
        # Rebar cover - should be 20-40mm
        rc = float(m.get('rebar_cover_mm', 30))
        if rc < 15: score += 30
        elif rc < 20: score += 15
        elif rc > 50: score += 10
        # Crack width - should be < 0.3mm
        cw = float(m.get('crack_width_mm', 0.1))
        if cw > 0.5: score += 30
        elif cw > 0.3: score += 20
        elif cw > 0.2: score += 10
        return min(100.0, score)
    
    def _risk_level(self, score):
        if score >= 70: return 'CRITICAL'
        if score >= 50: return 'HIGH'
        if score >= 30: return 'MEDIUM'
        if score >= 15: return 'LOW'
        return 'MINIMAL'
    
    def _recommendations(self, m, score):
        recs = []
        if score >= 70:
            recs.append('Immediate structural reinforcement required')
            recs.append('Engage certified structural engineer within 48 hours')
        elif score >= 50:
            recs.append('Schedule detailed structural assessment within 2 weeks')
            recs.append('Review crack propagation patterns')
        elif score >= 30:
            recs.append('Monitor crack width monthly')
            recs.append('Verify rebar corrosion levels')
        else:
            recs.append('Routine inspection every 12 months')
        return recs

store = InspectionStore()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {fmt % args}")
    
    def _send(self, code, body):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode())
    
    def do_GET(self):
        if self.path == '/health':
            self._send(200, {'status': 'ok', 'time': time.time()})
        elif self.path.startswith('/api/inspections/'):
            iid = self.path.split('/')[-1]
            record = store.get_inspection(iid)
            if record:
                self._send(200, record)
            else:
                self._send(404, {'error': 'Not found'})
        elif self.path == '/api/assessments':
            results = list(store.assessments.values())
            self._send(200, {'count': len(results), 'items': results})
        elif self.path.startswith('/api/assessments/'):
            aid = self.path.split('/')[-1]
            record = store.assessments.get(aid)
            if record:
                self._send(200, record)
            else:
                self._send(404, {'error': 'Not found'})
        else:
            self._send(404, {'error': 'Not found', 'endpoints': [
                'GET /health',
                'POST /api/inspections',
                'GET /api/inspections/<id>',
                'POST /api/assessments',
                'GET /api/assessments',
                'GET /api/assessments/<id>',
            ]})
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(content_length)
        try:
            body = json.loads(raw) if raw else {}
        except:
            self._send(400, {'error': 'Invalid JSON'})
            return
        
        if self.path == '/api/inspections':
            record = store.create_inspection(body)
            self._send(201, record)
        elif self.path == '/api/assessments':
            record = store.create_assessment(body)
            self._send(201, record)
        else:
            self._send(404, {'error': 'Not found'})

if __name__ == '__main__':
    port = int(os.environ.get('FLASK_PORT', 8080))
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print(f"jianzhu-saas API server running on port {port}")
    print(f"Endpoints: /health, /api/inspections, /api/assessments")
    server.serve_forever()
