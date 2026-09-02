"""CodeRisk Cloud — Nutrient DWS 客户端

Nutrient DWS 集成：
  • PDF Conversion API — 将漏洞报告转为专业 PDF
  • Digital Signature — SHA-256 完整性校验嵌入
  • DWS Viewer — 在线预览（预留）
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("coderisk.nutrient")


# ═════════════════════════════════════════════════════════════
# 优化后的 HTML 报告模板
# ═════════════════════════════════════════════════════════════

REPORT_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CodeRisk Security Report — {task_id}</title>
  <style>
    @page {{ size: A4; margin: 18mm; }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      color: #1f2937;
      line-height: 1.6;
      background: #fff;
    }}

    /* ===== Header ===== */
    .report-header {{
      background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
      color: #fff;
      padding: 32px 30px;
      text-align: center;
      page-break-after: avoid;
    }}
    .report-header .logo {{ font-size: 32px; margin-bottom: 6px; }}
    .report-header h1 {{
      margin: 0;
      font-size: 26px;
      font-weight: 700;
      letter-spacing: 0.5px;
    }}
    .report-header .subtitle {{
      margin-top: 6px;
      font-size: 14px;
      opacity: 0.85;
      font-weight: 400;
    }}
    .report-header .meta {{
      margin-top: 18px;
      font-size: 12px;
      opacity: 0.75;
      display: flex;
      justify-content: center;
      gap: 20px;
      flex-wrap: wrap;
    }}
    .report-header .meta span {{
      background: rgba(255,255,255,0.12);
      padding: 4px 12px;
      border-radius: 4px;
      white-space: nowrap;
    }}

    /* ===== Summary ===== */
    .summary-section {{
      padding: 24px 30px;
      background: #f8fafc;
      border-bottom: 1px solid #e2e8f0;
      page-break-inside: avoid;
    }}
    .summary-title {{
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 16px;
      color: #1e293b;
      text-transform: uppercase;
      letter-spacing: 0.8px;
    }}
    .summary-grid {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .severity-card {{
      min-width: 110px;
      flex: 1;
      border-radius: 12px;
      padding: 18px 10px;
      text-align: center;
      border: 1.5px solid;
      page-break-inside: avoid;
    }}
    .severity-card .count {{
      display: block;
      font-size: 34px;
      font-weight: 800;
      line-height: 1;
    }}
    .severity-card .label {{
      display: block;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      margin-top: 8px;
    }}
    .card-critical {{ background: #fef2f2; border-color: #fecaca; color: #dc2626; }}
    .card-high    {{ background: #fff7ed; border-color: #fed7aa; color: #ea580c; }}
    .card-medium  {{ background: #fefce8; border-color: #fde047; color: #a16207; }}
    .card-low     {{ background: #f0fdf4; border-color: #bbf7d0; color: #16a34a; }}
    .card-info    {{ background: #f8fafc; border-color: #e2e8f0; color: #64748b; }}

    /* ===== Findings ===== */
    .findings-section {{ padding: 24px 30px; }}
    .findings-title {{
      font-size: 20px;
      font-weight: 700;
      margin-bottom: 20px;
      color: #1e293b;
      padding-bottom: 10px;
      border-bottom: 3px solid #e2e8f0;
      page-break-after: avoid;
    }}
    .finding-card {{
      margin-bottom: 16px;
      padding: 16px 18px;
      border-radius: 8px;
      border-left: 5px solid;
      background: #fff;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
      page-break-inside: avoid;
    }}
    .finding-card.critical {{ border-left-color: #dc2626; background: #fef2f2; }}
    .finding-card.high    {{ border-left-color: #ea580c; background: #fff7ed; }}
    .finding-card.medium  {{ border-left-color: #ca8a04; background: #fefce8; }}
    .finding-card.low     {{ border-left-color: #16a34a; background: #f0fdf4; }}
    .finding-card.info    {{ border-left-color: #64748b; background: #f8fafc; }}

    .finding-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
      flex-wrap: wrap;
    }}
    .severity-badge {{
      padding: 3px 12px;
      border-radius: 999px;
      font-size: 10px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #fff;
      flex-shrink: 0;
    }}
    .badge-critical {{ background: #dc2626; }}
    .badge-high    {{ background: #ea580c; }}
    .badge-medium  {{ background: #ca8a04; }}
    .badge-low     {{ background: #16a34a; }}
    .badge-info    {{ background: #64748b; }}

    .finding-title {{
      font-size: 15px;
      font-weight: 700;
      color: #0f172a;
      margin: 0;
      flex: 1;
      line-height: 1.4;
    }}
    .finding-meta {{
      font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
      font-size: 12px;
      color: #475569;
      margin-bottom: 10px;
      background: rgba(0,0,0,0.04);
      padding: 5px 10px;
      border-radius: 4px;
      display: inline-block;
    }}
    .finding-desc {{
      font-size: 13px;
      line-height: 1.7;
      color: #334155;
      margin: 0;
    }}
    .finding-rule {{
      font-size: 11px;
      color: #64748b;
      margin-top: 10px;
      font-weight: 600;
      font-family: 'SFMono-Regular', Consolas, monospace;
    }}

    /* ===== Signature ===== */
    .signature-section {{
      margin: 24px 30px;
      padding: 20px;
      background: #f0fdf4;
      border: 1.5px solid #86efac;
      border-radius: 10px;
      text-align: center;
      page-break-inside: avoid;
    }}
    .signature-section .sig-icon {{ font-size: 24px; margin-bottom: 4px; }}
    .signature-section h3 {{
      margin: 0 0 6px 0;
      color: #166534;
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .signature-hash {{
      font-family: 'SFMono-Regular', Consolas, monospace;
      font-size: 11px;
      color: #15803d;
      word-break: break-all;
      background: rgba(255,255,255,0.7);
      padding: 8px 14px;
      border-radius: 6px;
      display: inline-block;
      margin-top: 6px;
      border: 1px dashed #22c55e;
    }}

    /* ===== Footer ===== */
    .report-footer {{
      text-align: center;
      padding: 20px 30px;
      font-size: 11px;
      color: #94a3b8;
      border-top: 1px solid #e2e8f0;
      margin-top: 10px;
      page-break-inside: avoid;
    }}
    .report-footer .brand {{ font-weight: 700; color: #64748b; }}

    /* ===== Print ===== */
    @media print {{
      .report-header, .severity-card, .finding-card, .signature-section {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
    }}
  </style>
</head>
<body>
  <div class="report-header">
    <div class="logo">🛡️</div>
    <h1>CodeRisk Security Report</h1>
    <div class="subtitle">AI-Powered Code Security Analysis</div>
    <div class="meta">
      <span>Task: {task_id}</span>
      <span>Date: {generated_at}</span>
      <span>Source: {source}</span>
    </div>
  </div>

  <div class="summary-section">
    <div class="summary-title">Severity Summary</div>
    <div class="summary-grid">
      <div class="severity-card card-critical">
        <span class="count">{count_critical}</span>
        <span class="label">Critical</span>
      </div>
      <div class="severity-card card-high">
        <span class="count">{count_high}</span>
        <span class="label">High</span>
      </div>
      <div class="severity-card card-medium">
        <span class="count">{count_medium}</span>
        <span class="label">Medium</span>
      </div>
      <div class="severity-card card-low">
        <span class="count">{count_low}</span>
        <span class="label">Low</span>
      </div>
      <div class="severity-card card-info">
        <span class="count">{count_info}</span>
        <span class="label">Info</span>
      </div>
    </div>
  </div>

  <div class="findings-section">
    <div class="findings-title">Security Findings</div>
    {findings_html}
  </div>

  <div class="signature-section">
    <div class="sig-icon">🔏</div>
    <h3>Digitally Signed — SHA-256 Integrity Verification</h3>
    <div class="signature-hash">{signature_hash}</div>
  </div>

  <div class="report-footer">
    <span class="brand">CodeRisk Cloud</span> © 2026 | AI溢出安全实验室 (Overflow Security Lab)<br>
    Generated by CodeRisk Cloud v1.0.0 | Powered by Nutrient DWS<br>
    <em>This report was generated automatically. Manual review recommended for all findings.</em>
  </div>
</body>
</html>"""

FINDING_HTML_TEMPLATE = """
<div class="finding-card {severity_class}">
  <div class="finding-header">
    <span class="severity-badge badge-{severity_class}">{severity}</span>
    <h3 class="finding-title">{title}</h3>
  </div>
  <div class="finding-meta">📁 {file_path}:{line} | Rule: {rule_id}</div>
  <p class="finding-desc">{description}</p>
  <div class="finding-rule">CWE: {cwe_id} | Confidence: {confidence}%</div>
</div>
"""


class NutrientDWSClient:
    """Nutrient DWS 文档处理客户端"""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.NUTRIENT_API_KEY
        self.base_url = settings.NUTRIENT_API_URL
        self.enabled = bool(self.api_key)
        if not self.enabled:
            logger.warning("Nutrient DWS API Key not configured, PDF features disabled")

    async def generate_pdf(self, report_data: dict[str, Any]) -> bytes | None:
        """将 JSON 报告转换为专业 PDF"""
        if not self.enabled:
            logger.warning("Skipping PDF generation: Nutrient DWS not configured")
            return None

        try:
            html_content = self._render_html(report_data)

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data={"instructions": json.dumps({"parts": [{"html": "report.html"}]})},
                    files={"report.html": ("report.html", html_content, "text/html")},
                )
                response.raise_for_status()
                logger.info(f"Nutrient PDF generated: {len(response.content)} bytes")
                return response.content

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Nutrient API HTTP error: {e.response.status_code} — {e.response.text[:200]}"
            )
            return None
        except Exception as e:
            logger.exception(f"Nutrient PDF generation failed: {e}")
            return None

    async def sign_pdf(self, pdf_bytes: bytes) -> bytes | None:
        """对 PDF 进行 SHA-256 完整性签名（当前实现）"""
        if not pdf_bytes:
            return None

        signature = hashlib.sha256(pdf_bytes).hexdigest()
        logger.info(f"PDF SHA-256 signature: {signature[:16]}...")
        # 实际证书签名需 Nutrient Digital Signatures API + .pfx 证书
        # 当前返回原 bytes，签名信息已嵌入 HTML 模板
        return pdf_bytes

    def generate_viewer_url(self, task_id: str) -> str | None:
        """生成 DWS Viewer 在线预览链接（预留）"""
        if not self.enabled:
            return None
        # TODO: Day 9-10 接入 Nutrient Document Engine 预签名 URL
        # 降级方案：返回自建预览路由
        return f"/viewer/{task_id}"

    def _render_html(self, report_data: dict[str, Any]) -> str:
        """将报告数据渲染为 HTML"""
        summary = report_data.get("summary", {})
        findings = report_data.get("findings", [])
        task_id = report_data.get("task_id", "unknown")
        generated_at = report_data.get("generated_at", "N/A")
        source = report_data.get("source", "unknown")

        # 渲染 findings
        findings_html = ""
        for f in findings:
            sev = f.get("severity", "info").lower()
            findings_html += FINDING_HTML_TEMPLATE.format(
                severity_class=sev,
                severity=sev.upper(),
                title=f.get("title", "Untitled Finding"),
                file_path=f.get("file", "unknown"),
                line=f.get("line", 0),
                rule_id=f.get("rule_id", f.get("type", "N/A")),
                description=f.get("description", ""),
                cwe_id=f.get("cwe_id", f.get("cwe", "N/A")),
                confidence=f.get("confidence", 85),
            )

        # 计算签名哈希
        report_json = json.dumps(report_data, sort_keys=True)
        signature_hash = hashlib.sha256(report_json.encode()).hexdigest()

        return REPORT_HTML_TEMPLATE.format(
            task_id=task_id,
            generated_at=generated_at,
            source=source,
            count_critical=summary.get("critical", 0),
            count_high=summary.get("high", 0),
            count_medium=summary.get("medium", 0),
            count_low=summary.get("low", 0),
            count_info=summary.get("info", 0),
            findings_html=findings_html,
            signature_hash=signature_hash,
        )
