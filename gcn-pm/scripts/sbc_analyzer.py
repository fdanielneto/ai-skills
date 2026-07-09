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

def analyze_b1(raw_data):
    REASON_MAP = {
        "16": "Normal call clearing",
        "41": "Temporary failure",
        "1": "Unallocated (unassigned) number",
        "17": "User busy",
        "31": "Normal, unspecified",
        "18": "No user responding",
        "102": "Recovery on timer expiry",
        "20": "Subscriber absent",
        "21": "Call rejected",
        "19": "No answer from user (user alerted)"
    }
    
    ribbon_buckets = raw_data.get('aggregations', {}).get('ribbons', {}).get('buckets', {})

    def make_table(ribbon_key, title):
        data = ribbon_buckets.get(ribbon_key, {})
        total = data.get('doc_count', 0)
        buckets = data.get('reasons', {}).get('buckets', [])
        
        html = []
        html.append(f'<div style="font-size: 0.85em;">')
        html.append(f'  <table>')
        html.append(f'    <thead>')
        html.append(f'      <tr>')
        html.append(f'        <th colspan="2"><strong>{title}</strong></th>')
        html.append(f'      </tr>')
        html.append(f'    </thead>')
        html.append(f'    <tbody>')
        html.append(f'      <tr>')
        html.append(f'        <td>Total calls (STOP)</td>')
        html.append(f'        <td>{format_number(total)}</td>')
        html.append(f'      </tr>')
        for b in buckets:
            code = b['key']
            count = b['doc_count']
            name = REASON_MAP.get(code, f"Code {code}")
            pct = (count / total * 100) if total > 0 else 0
            html.append(f'      <tr>')
            html.append(f'        <td>{name} ({code})</td>')
            html.append(f'        <td>{format_number(count)} ({pct:.1f}%)</td>')
            html.append(f'      </tr>')
        html.append(f'    </tbody>')
        html.append(f'  </table>')
        html.append(f'</div>')
        return '\n'.join(html)

    print("<ac:layout>")
    print("  <ac:layout-section ac:type=\"two_equal\">")
    print("    <ac:layout-cell>")
    print(make_table("EU", "Ribbon EU"))
    print("    </ac:layout-cell>")
    print("    <ac:layout-cell>")
    print(make_table("US", "Ribbon US"))
    print("    </ac:layout-cell>")
    print("  </ac:layout-section>")
    print("  <ac:layout-section ac:type=\"two_equal\">")
    print("    <ac:layout-cell>")
    print(make_table("APAC", "Ribbon APAC"))
    print("    </ac:layout-cell>")
    print("    <ac:layout-cell>")
    print(make_table("LATAM", "Ribbon LATAM"))
    print("    </ac:layout-cell>")
    print("  </ac:layout-section>")
    print("</ac:layout>")

def analyze_b2(raw_data, sbc_name):
    """Per-SBC call attempts timeline -> PNG + ready-to-embed <ac:image> tag."""
    buckets = raw_data.get('aggregations', {}).get('timeline', {}).get('buckets', [])
    payload = {
        "lines": [{
            "label": sbc_name,
            "points": [{"x": b.get('key_as_string', ''), "y": b.get('doc_count', 0)} for b in buckets],
        }]
    }

    os.makedirs("output", exist_ok=True)
    out_path = f"output/sbc_timeline_{sbc_name}.png"
    plot_helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plot_helper.py")
    try:
        subprocess.run(
            [sys.executable, plot_helper, f"Call Attempts — {sbc_name}", out_path, "Time", "calls", json.dumps(payload)],
            check=True, capture_output=True, text=True,
        )
    except Exception as e:
        sys.exit(f"ERROR: chart generation failed for {sbc_name}: {e}")

    print(f'<ac:image ac:align="center" ac:width="950"><ri:attachment ri:filename="{os.path.basename(out_path)}"/></ac:image>')

def main():
    if len(sys.argv) < 2:
        print("Usage: sbc_analyzer.py <mode> [json_file]")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "b2":
        if len(sys.argv) < 3:
            sys.exit("Usage: sbc_analyzer.py b2 <SBC_NAME> [json_file]")
        sbc_name = sys.argv[2]
        if len(sys.argv) > 3:
            with open(sys.argv[3], 'r') as f:
                raw_data = json.load(f)
        else:
            raw_data = json.load(sys.stdin)
        analyze_b2(raw_data, sbc_name)
        return

    if len(sys.argv) > 2:
        with open(sys.argv[2], 'r') as f:
            raw_data = json.load(f)
    else:
        raw_data = json.load(sys.stdin)

    if mode == "a1-a3":
        analyze_a1_a3(raw_data)
    elif mode == "b1":
        analyze_b1(raw_data)
    else:
        print("Mode not implemented yet")

if __name__ == "__main__":
    main()
