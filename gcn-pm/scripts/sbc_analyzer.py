#!/usr/bin/env python3
import sys
import json
import os
import subprocess
from datetime import datetime

# Substitui o kb-proxy.js
# Pega nos dados (via stdin ou usando requests para o elasticsearch proxy)
# Executa as regras matemáticas e retorna Markdown limpo

def format_number(n):
    return f"{n:,}"

def analyze_a1_a3(raw_data):
    total = raw_data['hits']['total']
    if isinstance(total, dict):
        total = total['value']
        
    media = raw_data.get('aggregations', {}).get('media_anchoring', {}).get('doc_count', 0)
    buckets = raw_data.get('aggregations', {}).get('disconnect_reasons', {}).get('buckets', [])
    
    print("### A-1. Total Call Attempts & Media Anchoring")
    print("| Metric | Value |")
    print("|--------|-------|")
    print(f"| Total Call Attempts (all) | {format_number(total)} |")
    print(f"| Total Media Anchoring Calls (all) | {format_number(media)} |")
    print("")
    print("### A-3. Call Disconnect Reason (all regions) — Top 10")
    print("| Metric | Value |")
    print("|--------|-------|")
    print(f"| Total calls (STOP) | {format_number(total)} |")
    for b in buckets:
        count = b['doc_count']
        pct = (count / total * 100) if total > 0 else 0
        if pct >= 0.5: # Ignora erros inferiores a 0.5% (exemplo de filtro para poupar tokens)
            print(f"| {b['key']} | {format_number(count)} ({pct:.1f}%) |")

def main():
    if len(sys.argv) < 2:
        print("Usage: sbc_analyzer.py <mode> [json_file]")
        sys.exit(1)
        
    mode = sys.argv[1]
    
    if len(sys.argv) > 2:
        with open(sys.argv[2], 'r') as f:
            raw_data = json.load(f)
    else:
        raw_data = json.load(sys.stdin)
        
    if mode == "a1-a3":
        analyze_a1_a3(raw_data)
    else:
        print("Mode not implemented yet")

if __name__ == "__main__":
    main()
