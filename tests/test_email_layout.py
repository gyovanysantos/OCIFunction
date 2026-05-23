"""Quick test: renders the Centrilogic email template and sends it via ACS."""
import asyncio
import os
import re
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'), override=False)

import markdown as md_lib
from azure.communication.email.aio import EmailClient as ACSEmailClient

# ── Centrilogic template (mirrors agents/api.py) ──────────────────────────────

_HTML_TEMPLATE = """\
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#0d0e12">
<tr><td>
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#13151c">
<tr>
  <td width="4" bgcolor="#f47c2f">&nbsp;</td>
  <td>
    <table width="100%" cellpadding="12" cellspacing="0">
    <tr>
      <td valign="middle">
        <table cellpadding="0" cellspacing="0">
        <tr>
          <td bgcolor="#f47c2f" width="36" height="28" align="center" valign="middle">
            <font color="#ffffff" size="2"><b>CL</b></font>
          </td>
          <td width="10">&nbsp;</td>
          <td>
            <font color="#f47c2f" size="5"><b>JDE INTEGRITY ANALYSIS</b></font><br>
            <font color="#8a8a9a" size="2">{report_type} &nbsp;|&nbsp; {company}</font>
          </td>
        </tr>
        </table>
      </td>
      <td align="right" valign="middle">
        {status_badge}
      </td>
    </tr>
    </table>
  </td>
</tr>
</table>
<table width="100%" cellpadding="16" cellspacing="0" bgcolor="#1e2130">
<tr>
  <td>
    <font color="#e8e6de">{body_html}</font>
  </td>
</tr>
</table>
<table width="100%" cellpadding="8" cellspacing="0" bgcolor="#0d0e12">
<tr>
  <td>
    <font color="#8a8a9a" size="1">Generated {timestamp} &nbsp;|&nbsp; JDE AI Integrity Analyzer v2.0</font>
  </td>
  <td align="right">
    <font color="#f47c2f" size="1"><b>Centrilogic</b></font>
  </td>
</tr>
</table>
</td></tr>
</table>"""

_BADGE_ISSUES = (
    '<table cellpadding="4" cellspacing="0" bgcolor="#f25353">'
    '<tr><td><font color="#ffffff"><b>ISSUES FOUND</b></font></td></tr>'
    '</table>'
)
_BADGE_CLEAR = (
    '<table cellpadding="4" cellspacing="0" bgcolor="#2ddc7c">'
    '<tr><td><font color="#0d0e12"><b>ALL CLEAR</b></font></td></tr>'
    '</table>'
)


def _sanitize(html: str) -> str:
    html = re.sub(r'\s+style="[^"]*"', '', html)
    html = re.sub(r'<h1[^>]*>(.*?)</h1>', r'<p><font color="#f47c2f" size="4"><b>\1</b></font></p>', html)
    html = re.sub(r'<h2[^>]*>(.*?)</h2>', r'<p><font color="#f47c2f" size="3"><b>\1</b></font></p>', html)
    html = re.sub(r'<h3[^>]*>(.*?)</h3>', r'<p><font color="#f9a85d"><b>\1</b></font></p>', html)
    html = html.replace('<strong>', '<b>').replace('</strong>', '</b>')
    html = html.replace('<em>', '<i>').replace('</em>', '</i>')
    html = re.sub(r'<span[^>]*>', '', html).replace('</span>', '')
    html = re.sub(r'<code[^>]*>', '', html).replace('</code>', '')
    html = re.sub(r'<pre[^>]*>', '', html).replace('</pre>', '')
    return html


def build_html(object_name: str, checker: str, analysis_md: str) -> str:
    parts = object_name.replace(".pdf", "").replace(".PDF", "").split("_")
    report_type = parts[0] if parts else "Unknown"
    company = parts[1] if len(parts) >= 2 else "Unknown"
    badge = _BADGE_ISSUES if checker == "Yes" else _BADGE_CLEAR
    body = _sanitize(md_lib.markdown(analysis_md, extensions=["tables", "fenced_code"]))
    ts = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    return _HTML_TEMPLATE.format(
        report_type=report_type, company=company,
        status_badge=badge, body_html=body, timestamp=ts,
    )


async def send(to: str, subject: str, html: str) -> None:
    conn = os.getenv("ACS_CONNECTION_STRING")
    from_addr = os.getenv(
        "EMAIL_FROM_ADDRESS",
        "DoNotReply@436186b1-bceb-48e0-bded-1fcbb6fea3a9.azurecomm.net",
    )
    async with ACSEmailClient.from_connection_string(conn) as client:
        poller = await client.begin_send({
            "senderAddress": from_addr,
            "recipients": {"to": [{"address": to}]},
            "content": {"subject": subject, "html": html},
        })
        result = await poller.result()
    print(f"Sent -> {to} (id={result.get('id', '?')})")


# ── Mock data ─────────────────────────────────────────────────────────────────

MOCK_OBJECT = "R047001A_SCH0001_32188_PDF.pdf"
MOCK_ANALYSIS = """\
## Executive Summary
The AP/GL integrity report for company **SCH0001** contains **3 discrepancies** requiring immediate review.

## Discrepancies Found

### 1. Unposted Vouchers in F0411
Account 1000.001 has 2 unposted vouchers totalling **$14,520.00**.

### 2. GL Balance Mismatch
F0902 balance for account 4000.002 does not match F0911 actuals. Variance: **$320.50**.

### 3. Missing Document Reference
Document type PV, document number 123456 has no matching record in F0411.

## Recommended Actions
- Post or void unposted vouchers before period close
- Investigate GL balance variance with accounting team
- Locate or recreate missing document reference
"""


async def main():
    html = build_html(MOCK_OBJECT, "Yes", MOCK_ANALYSIS)

    out = os.path.join(os.path.dirname(__file__), "test_email_layout.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML preview saved -> {out}")

    await send(
        "gsantos@centrilogic.com",
        "TEST — JDE Integrity Report — R047001A (SCH0001) — ISSUES FOUND",
        html,
    )


if __name__ == "__main__":
    asyncio.run(main())
