"""
Security Scanner: Multi-language static application security testing (SAST).

Pattern-based scanner covering OWASP Top 10, secret detection, cryptographic
weaknesses, injection patterns, and insecure configuration across:
  Python, JavaScript/TypeScript, Go, Rust, Solidity

Each pattern maps to a CWE ID, severity, and OWASP category.
No external tool dependencies — pure regex-based for reproducibility.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

# ═══════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class VulnPattern:
    """A vulnerability detection pattern."""

    id: str
    cwe: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    owasp: str  # A01-A10 category
    category: str  # Human-readable category
    description: str
    pattern: str  # Regex pattern
    languages: list[str]  # ["python", "javascript", ...] or ["*"]
    false_positive_pattern: str | None = None  # Regex to suppress FPs


@dataclass
class SecurityFinding:
    """A single security finding in a file."""

    pattern_id: str
    cwe: str
    severity: str
    owasp: str
    category: str
    description: str
    file_path: str
    line_number: int
    snippet: str
    language: str


@dataclass
class SecurityScanResult:
    """Aggregate security scan results for a project."""

    project_id: str
    source: str
    total_findings: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    kloc: float = 0.0
    total_files_scanned: int = 0
    security_debt_density: float = 0.0  # findings per KLOC
    secret_count: int = 0
    injection_count: int = 0
    crypto_weakness_count: int = 0
    auth_issue_count: int = 0
    config_issue_count: int = 0
    findings: list[SecurityFinding] = field(default_factory=list)

    def compute_aggregates(self):
        """Recompute aggregate counts from findings list."""
        self.total_findings = len(self.findings)
        self.critical = sum(1 for f in self.findings if f.severity == "CRITICAL")
        self.high = sum(1 for f in self.findings if f.severity == "HIGH")
        self.medium = sum(1 for f in self.findings if f.severity == "MEDIUM")
        self.low = sum(1 for f in self.findings if f.severity == "LOW")
        self.secret_count = sum(
            1 for f in self.findings if f.category == "Secrets"
        )
        self.injection_count = sum(
            1 for f in self.findings if f.category == "Injection"
        )
        self.crypto_weakness_count = sum(
            1 for f in self.findings if f.category == "Cryptography"
        )
        self.auth_issue_count = sum(
            1 for f in self.findings if f.category == "Authentication"
        )
        self.config_issue_count = sum(
            1 for f in self.findings if f.category == "Configuration"
        )
        if self.kloc > 0:
            self.security_debt_density = self.total_findings / self.kloc


# ═══════════════════════════════════════════════════════════════════════
# VULNERABILITY PATTERN REGISTRY
# ═══════════════════════════════════════════════════════════════════════

# Skip directories
SKIP_DIRS: Final[set[str]] = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", "vendor", "target",
    ".tox", ".mypy_cache", ".pytest_cache", "coverage", ".cache",
    "migrations", "static", "assets", "public", "out",
}

# File extensions per language
LANG_EXTENSIONS: Final[dict[str, set[str]]] = {
    "python": {".py"},
    "javascript": {".js", ".jsx", ".mjs", ".cjs"},
    "typescript": {".ts", ".tsx"},
    "go": {".go"},
    "rust": {".rs"},
    "solidity": {".sol"},
}

# Max file size to scan (500KB)
MAX_SCAN_SIZE: Final[int] = 500 * 1024

# ── SECRET DETECTION PATTERNS ──────────────────────────────────────────

SECRET_PATTERNS: list[VulnPattern] = [
    VulnPattern(
        id="SEC-001", cwe="CWE-798", severity="CRITICAL",
        owasp="A07", category="Secrets",
        description="AWS Access Key ID hardcoded",
        pattern=r"(?:AKIA|ASIA)[0-9A-Z]{16}",
        languages=["*"],
    ),
    VulnPattern(
        id="SEC-002", cwe="CWE-798", severity="CRITICAL",
        owasp="A07", category="Secrets",
        description="AWS Secret Access Key hardcoded",
        pattern=r"""(?:aws_secret_access_key|secret_key)\s*[=:]\s*['"][A-Za-z0-9/+=]{40}['"]""",
        languages=["*"],
        false_positive_pattern=r"(?:example|placeholder|xxx|your[-_]?key|CHANGE[-_]?ME)",
    ),
    VulnPattern(
        id="SEC-003", cwe="CWE-798", severity="CRITICAL",
        owasp="A07", category="Secrets",
        description="GitHub token hardcoded",
        pattern=r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}",
        languages=["*"],
    ),
    VulnPattern(
        id="SEC-004", cwe="CWE-798", severity="CRITICAL",
        owasp="A07", category="Secrets",
        description="Private key embedded in source",
        pattern=r"-----BEGIN\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE\s+KEY-----",
        languages=["*"],
    ),
    VulnPattern(
        id="SEC-005", cwe="CWE-798", severity="HIGH",
        owasp="A07", category="Secrets",
        description="Generic API key/secret assignment",
        pattern=r"""(?:api[_-]?key|api[_-]?secret|auth[_-]?token|access[_-]?token)\s*[=:]\s*['"][A-Za-z0-9_\-/.+=]{16,}['"]""",
        languages=["*"],
        false_positive_pattern=r"(?:example|placeholder|xxx|your[-_]?key|CHANGE[-_]?ME|test|fake|dummy|process\.env|os\.environ|os\.getenv)",
    ),
    VulnPattern(
        id="SEC-006", cwe="CWE-798", severity="HIGH",
        owasp="A07", category="Secrets",
        description="Hardcoded password in source",
        pattern=r"""(?:password|passwd|pwd)\s*[=:]\s*['"][^'"]{8,}['"]""",
        languages=["*"],
        false_positive_pattern=r"(?:example|placeholder|xxx|CHANGE[-_]?ME|test|fake|dummy|\*+|process\.env|os\.environ|os\.getenv|argparse|input\(|getpass)",
    ),
    VulnPattern(
        id="SEC-007", cwe="CWE-798", severity="HIGH",
        owasp="A07", category="Secrets",
        description="Database connection string with credentials",
        pattern=r"""(?:postgresql|mysql|mongodb|redis|amqp)://[^:]+:[^@]+@[^/\s'"]+""",
        languages=["*"],
        false_positive_pattern=r"(?:localhost|127\.0\.0\.1|example\.com|placeholder|user:pass)",
    ),
    VulnPattern(
        id="SEC-008", cwe="CWE-798", severity="HIGH",
        owasp="A07", category="Secrets",
        description="Slack/Discord/Telegram bot token hardcoded",
        pattern=r"""(?:xox[bpsar]-[A-Za-z0-9-]{10,}|discord[_.]?(?:token|webhook)[^=]*[=:]\s*['"][^'"]{20,}['"]|bot_token\s*[=:]\s*['"][0-9]+:[A-Za-z0-9_-]{35}['"])""",
        languages=["*"],
    ),
    VulnPattern(
        id="SEC-009", cwe="CWE-798", severity="HIGH",
        owasp="A07", category="Secrets",
        description="JWT secret hardcoded",
        pattern=r"""(?:jwt[_-]?secret|secret[_-]?key|signing[_-]?key)\s*[=:]\s*['"][A-Za-z0-9_\-/.+=]{16,}['"]""",
        languages=["*"],
        false_positive_pattern=r"(?:example|placeholder|xxx|CHANGE[-_]?ME|test|fake|process\.env|os\.environ|os\.getenv|your[-_]?secret)",
    ),
    VulnPattern(
        id="SEC-010", cwe="CWE-312", severity="MEDIUM",
        owasp="A02", category="Secrets",
        description="Sensitive data logged or printed",
        pattern=r"""(?:print|log(?:ger)?\.(?:info|debug|warn|error)|console\.log|fmt\.Print)\s*\([^)]*(?:password|secret|token|credential|api[_-]?key)""",
        languages=["*"],
        false_positive_pattern=r"(?:#|//|/\*)\s*(?:print|log)",
    ),
]

# ── INJECTION PATTERNS ─────────────────────────────────────────────────

INJECTION_PATTERNS: list[VulnPattern] = [
    # Python injection
    VulnPattern(
        id="INJ-001", cwe="CWE-78", severity="CRITICAL",
        owasp="A03", category="Injection",
        description="OS command injection via shell=True",
        pattern=r"""subprocess\.(?:call|run|Popen|check_output|check_call)\s*\([^)]*shell\s*=\s*True""",
        languages=["python"],
        false_positive_pattern=r"#.*subprocess",
    ),
    VulnPattern(
        id="INJ-002", cwe="CWE-78", severity="CRITICAL",
        owasp="A03", category="Injection",
        description="OS command execution via os.system()",
        pattern=r"""os\.system\s*\(\s*(?:f['"]|[^'"]*\+|[^'"]*\.format|[^'"]*%)""",
        languages=["python"],
    ),
    VulnPattern(
        id="INJ-003", cwe="CWE-95", severity="CRITICAL",
        owasp="A03", category="Injection",
        description="Code injection via eval()",
        pattern=r"""\beval\s*\(\s*(?!['"][^'"]*['"]\s*\))""",
        languages=["python", "javascript", "typescript"],
        false_positive_pattern=r"(?:#|//)\s*.*eval",
    ),
    VulnPattern(
        id="INJ-004", cwe="CWE-95", severity="CRITICAL",
        owasp="A03", category="Injection",
        description="Code injection via exec()",
        pattern=r"""\bexec\s*\(\s*(?!['"][^'"]*['"]\s*\))""",
        languages=["python"],
        false_positive_pattern=r"(?:#|//)\s*.*exec",
    ),
    VulnPattern(
        id="INJ-005", cwe="CWE-89", severity="HIGH",
        owasp="A03", category="Injection",
        description="SQL injection via string formatting",
        pattern=r"""(?:execute|query|raw|cursor\.execute)\s*\(\s*(?:f['"]|[^'"]*\+|[^'"]*\.format|[^'"]*%).*(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE)""",
        languages=["python"],
    ),
    VulnPattern(
        id="INJ-006", cwe="CWE-89", severity="HIGH",
        owasp="A03", category="Injection",
        description="SQL injection via string concatenation",
        pattern=r"""(?:query|sql|stmt)\s*(?:=|\+=)\s*['"].*(?:SELECT|INSERT|UPDATE|DELETE|WHERE).*['"]\s*\+""",
        languages=["python", "javascript", "typescript", "go"],
    ),
    VulnPattern(
        id="INJ-007", cwe="CWE-89", severity="HIGH",
        owasp="A03", category="Injection",
        description="SQL injection via Go Sprintf in query",
        pattern=r"""(?:db\.(?:Query|Exec|Prepare)|\.(?:Raw|Where|Having|Order))\s*\(\s*fmt\.Sprintf""",
        languages=["go"],
    ),
    # JavaScript XSS
    VulnPattern(
        id="INJ-008", cwe="CWE-79", severity="HIGH",
        owasp="A03", category="Injection",
        description="XSS via innerHTML assignment",
        pattern=r"""\.innerHTML\s*=\s*(?!['"`]\s*$)""",
        languages=["javascript", "typescript"],
        false_positive_pattern=r"""\.innerHTML\s*=\s*['"`]\s*['"`]""",
    ),
    VulnPattern(
        id="INJ-009", cwe="CWE-79", severity="HIGH",
        owasp="A03", category="Injection",
        description="XSS via dangerouslySetInnerHTML",
        pattern=r"dangerouslySetInnerHTML",
        languages=["javascript", "typescript"],
    ),
    VulnPattern(
        id="INJ-010", cwe="CWE-79", severity="HIGH",
        owasp="A03", category="Injection",
        description="XSS via document.write()",
        pattern=r"document\.write\s*\(",
        languages=["javascript", "typescript"],
    ),
    VulnPattern(
        id="INJ-011", cwe="CWE-78", severity="CRITICAL",
        owasp="A03", category="Injection",
        description="Command injection via child_process",
        pattern=r"""(?:child_process\.)?exec\s*\(\s*(?!['"][^'"]*['"]\s*[,)])""",
        languages=["javascript", "typescript"],
    ),
    VulnPattern(
        id="INJ-012", cwe="CWE-94", severity="HIGH",
        owasp="A03", category="Injection",
        description="Code injection via new Function()",
        pattern=r"new\s+Function\s*\(",
        languages=["javascript", "typescript"],
    ),
    # Go injection
    VulnPattern(
        id="INJ-013", cwe="CWE-78", severity="CRITICAL",
        owasp="A03", category="Injection",
        description="Command injection via exec.Command with variable",
        pattern=r"""exec\.Command\s*\(\s*[a-z]""",
        languages=["go"],
        false_positive_pattern=r"""exec\.Command\s*\(\s*['"]""",
    ),
    # Template injection
    VulnPattern(
        id="INJ-014", cwe="CWE-1336", severity="HIGH",
        owasp="A03", category="Injection",
        description="Server-side template injection (SSTI)",
        pattern=r"""(?:render_template_string|Template)\s*\(\s*(?!['"])""",
        languages=["python"],
    ),
]

# ── CRYPTOGRAPHY PATTERNS ──────────────────────────────────────────────

CRYPTO_PATTERNS: list[VulnPattern] = [
    VulnPattern(
        id="CRY-001", cwe="CWE-327", severity="HIGH",
        owasp="A02", category="Cryptography",
        description="Weak hash algorithm MD5 used",
        pattern=r"""(?:hashlib\.md5|MD5\.new|crypto\.createHash\s*\(\s*['"]md5['"]\)|md5\.New\(\)|Md5::new)""",
        languages=["*"],
        false_positive_pattern=r"(?:checksum|etag|cache|fingerprint|#|//)",
    ),
    VulnPattern(
        id="CRY-002", cwe="CWE-327", severity="MEDIUM",
        owasp="A02", category="Cryptography",
        description="Weak hash algorithm SHA1 used for security",
        pattern=r"""(?:hashlib\.sha1|SHA\.new|crypto\.createHash\s*\(\s*['"]sha1['"]\)|sha1\.New\(\)|Sha1::new)""",
        languages=["*"],
        false_positive_pattern=r"(?:checksum|etag|git|fingerprint|#|//)",
    ),
    VulnPattern(
        id="CRY-003", cwe="CWE-330", severity="HIGH",
        owasp="A02", category="Cryptography",
        description="Insecure random number generator for security context",
        pattern=r"""(?:random\.random|random\.randint|random\.choice|Math\.random)\s*\(""",
        languages=["python", "javascript", "typescript"],
        false_positive_pattern=r"(?:shuffle|sample|jitter|delay|color|position|test|mock|seed)",
    ),
    VulnPattern(
        id="CRY-004", cwe="CWE-295", severity="HIGH",
        owasp="A02", category="Cryptography",
        description="TLS/SSL certificate verification disabled",
        pattern=r"""(?:verify\s*=\s*False|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true|CERT_NONE)""",
        languages=["*"],
    ),
    VulnPattern(
        id="CRY-005", cwe="CWE-326", severity="MEDIUM",
        owasp="A02", category="Cryptography",
        description="Weak encryption key size (< 2048 bits)",
        pattern=r"""(?:generate_private_key|RSA\.generate|generateKeyPair)\s*\([^)]*(?:1024|512|768)""",
        languages=["*"],
    ),
    VulnPattern(
        id="CRY-006", cwe="CWE-327", severity="MEDIUM",
        owasp="A02", category="Cryptography",
        description="Deprecated/weak cipher (DES, RC4, Blowfish)",
        pattern=r"""(?:DES\.new|RC4|Blowfish|createCipheriv\s*\(\s*['"](?:des|rc4|bf))""",
        languages=["*"],
    ),
]

# ── AUTHENTICATION / ACCESS CONTROL ────────────────────────────────────

AUTH_PATTERNS: list[VulnPattern] = [
    VulnPattern(
        id="AUTH-001", cwe="CWE-287", severity="HIGH",
        owasp="A07", category="Authentication",
        description="Hardcoded admin/default credentials",
        pattern=r"""(?:admin|root|default)\s*[=:]\s*['"](?:admin|root|password|123456|default|test)['"]""",
        languages=["*"],
    ),
    VulnPattern(
        id="AUTH-002", cwe="CWE-306", severity="HIGH",
        owasp="A01", category="Authentication",
        description="CORS allow-all origin (*)",
        pattern=r"""(?:Access-Control-Allow-Origin['":\s]+\*|cors\(\s*\)|allow_origins\s*=\s*\[\s*['"]?\*['"]?\s*\])""",
        languages=["*"],
    ),
    VulnPattern(
        id="AUTH-003", cwe="CWE-613", severity="MEDIUM",
        owasp="A07", category="Authentication",
        description="JWT without expiration",
        pattern=r"""(?:jwt\.(?:encode|sign))\s*\([^)]*(?!exp)""",
        languages=["python", "javascript", "typescript"],
        false_positive_pattern=r"(?:exp|expiresIn|expires_delta|timedelta)",
    ),
    VulnPattern(
        id="AUTH-004", cwe="CWE-521", severity="MEDIUM",
        owasp="A07", category="Authentication",
        description="Weak password policy (min length < 8)",
        pattern=r"""(?:min[_-]?(?:length|len|size)|minlength)\s*[=:]\s*[1-7]\b""",
        languages=["*"],
    ),
    VulnPattern(
        id="AUTH-005", cwe="CWE-352", severity="HIGH",
        owasp="A01", category="Authentication",
        description="Missing CSRF protection on state-changing route",
        pattern=r"""@(?:app|router)\.(?:post|put|patch|delete)\s*\(['"][^'"]+['"]\)""",
        languages=["python"],
        false_positive_pattern=r"(?:csrf|CSRFProtect|WTF|token)",
    ),
    # Solidity-specific
    VulnPattern(
        id="AUTH-006", cwe="CWE-284", severity="CRITICAL",
        owasp="A01", category="Authentication",
        description="Solidity: tx.origin used for authentication",
        pattern=r"""tx\.origin""",
        languages=["solidity"],
        false_positive_pattern=r"(?://|/\*)\s*.*tx\.origin",
    ),
    VulnPattern(
        id="AUTH-007", cwe="CWE-284", severity="HIGH",
        owasp="A01", category="Authentication",
        description="Solidity: selfdestruct accessible without access control",
        pattern=r"""selfdestruct\s*\(""",
        languages=["solidity"],
        false_positive_pattern=r"(?:onlyOwner|require\s*\(|modifier)",
    ),
]

# ── INSECURE DESERIALIZATION / DATA INTEGRITY ──────────────────────────

DESER_PATTERNS: list[VulnPattern] = [
    VulnPattern(
        id="DES-001", cwe="CWE-502", severity="CRITICAL",
        owasp="A08", category="Deserialization",
        description="Unsafe pickle deserialization",
        pattern=r"""pickle\.(?:load|loads)\s*\(""",
        languages=["python"],
        false_positive_pattern=r"(?:trusted|safe|#.*pickle)",
    ),
    VulnPattern(
        id="DES-002", cwe="CWE-502", severity="HIGH",
        owasp="A08", category="Deserialization",
        description="Unsafe YAML loading (yaml.load without SafeLoader)",
        pattern=r"""yaml\.load\s*\([^)]*(?!Loader\s*=\s*(?:yaml\.)?SafeLoader|Loader\s*=\s*(?:yaml\.)?CSafeLoader)""",
        languages=["python"],
        false_positive_pattern=r"SafeLoader|safe_load|CSafeLoader",
    ),
    VulnPattern(
        id="DES-003", cwe="CWE-502", severity="HIGH",
        owasp="A08", category="Deserialization",
        description="Unsafe marshal/shelve deserialization",
        pattern=r"""(?:marshal\.loads|shelve\.open)\s*\(""",
        languages=["python"],
    ),
    VulnPattern(
        id="DES-004", cwe="CWE-502", severity="HIGH",
        owasp="A08", category="Deserialization",
        description="Unsafe JSON.parse on unvalidated input",
        pattern=r"""JSON\.parse\s*\(\s*(?:req\.|request\.|body\.|params\.)""",
        languages=["javascript", "typescript"],
    ),
]

# ── CONFIGURATION / MISCONFIGURATION ───────────────────────────────────

CONFIG_PATTERNS: list[VulnPattern] = [
    VulnPattern(
        id="CFG-001", cwe="CWE-489", severity="HIGH",
        owasp="A05", category="Configuration",
        description="Debug mode enabled in production code",
        pattern=r"""(?:DEBUG\s*=\s*True|debug\s*[=:]\s*true|\.run\s*\([^)]*debug\s*=\s*True)""",
        languages=["*"],
        false_positive_pattern=r"(?:if\s+|#|//|test|dev|development|\.env)",
    ),
    VulnPattern(
        id="CFG-002", cwe="CWE-200", severity="MEDIUM",
        owasp="A05", category="Configuration",
        description="Stack trace / verbose error exposed to client",
        pattern=r"""(?:traceback\.format_exc|stack\s*:\s*err\.stack|\.send\s*\(\s*err\.(?:message|stack))""",
        languages=["*"],
    ),
    VulnPattern(
        id="CFG-003", cwe="CWE-319", severity="HIGH",
        owasp="A02", category="Configuration",
        description="HTTP used instead of HTTPS for sensitive operation",
        pattern=r"""['"]http://[^'"]*(?:api|auth|login|payment|checkout|admin|token)""",
        languages=["*"],
        false_positive_pattern=r"(?:localhost|127\.0\.0\.1|0\.0\.0\.0|example\.com|test|mock)",
    ),
    VulnPattern(
        id="CFG-004", cwe="CWE-693", severity="MEDIUM",
        owasp="A05", category="Configuration",
        description="Missing security headers (helmet/CSP not configured)",
        pattern=r"""(?:app\.use\s*\(\s*express\.static|app\.listen)\s*\(""",
        languages=["javascript", "typescript"],
        false_positive_pattern=r"(?:helmet|csp|Content-Security-Policy|x-frame-options)",
    ),
    VulnPattern(
        id="CFG-005", cwe="CWE-532", severity="MEDIUM",
        owasp="A09", category="Configuration",
        description="Sensitive information in log statements",
        pattern=r"""(?:logger|log|console)\.\w+\s*\([^)]*(?:password|secret|token|key|credential|ssn|credit.?card)""",
        languages=["*"],
        false_positive_pattern=r"(?:mask|redact|\*+|#|//)",
    ),
    VulnPattern(
        id="CFG-006", cwe="CWE-1188", severity="MEDIUM",
        owasp="A05", category="Configuration",
        description="Insecure default: binding to 0.0.0.0",
        pattern=r"""(?:host\s*[=:]\s*['"]0\.0\.0\.0['"]|\.listen\s*\([^)]*0\.0\.0\.0|ListenAndServe\s*\(\s*['"](?::|\s*0\.0\.0\.0))""",
        languages=["*"],
    ),
    # Go-specific
    VulnPattern(
        id="CFG-007", cwe="CWE-319", severity="HIGH",
        owasp="A05", category="Configuration",
        description="Go HTTP server without TLS",
        pattern=r"""http\.ListenAndServe\s*\(""",
        languages=["go"],
        false_positive_pattern=r"(?:ListenAndServeTLS|TLS|tls)",
    ),
]

# ── PATH TRAVERSAL / FILE ACCESS ───────────────────────────────────────

PATH_PATTERNS: list[VulnPattern] = [
    VulnPattern(
        id="PTH-001", cwe="CWE-22", severity="HIGH",
        owasp="A01", category="Path Traversal",
        description="Path traversal via unsanitized user input in file path",
        pattern=r"""(?:open|readFile|readFileSync|os\.path\.join|path\.join)\s*\([^)]*(?:req\.|request\.|params\.|query\.|args\.|input)""",
        languages=["python", "javascript", "typescript"],
    ),
    VulnPattern(
        id="PTH-002", cwe="CWE-22", severity="HIGH",
        owasp="A01", category="Path Traversal",
        description="Path traversal: user input directly in file operation",
        pattern=r"""(?:send_file|send_from_directory|static_file)\s*\([^)]*(?:request\.|args\.get)""",
        languages=["python"],
    ),
    VulnPattern(
        id="PTH-003", cwe="CWE-73", severity="MEDIUM",
        owasp="A01", category="Path Traversal",
        description="File operation with external input not validated",
        pattern=r"""(?:shutil\.(?:copy|move|rmtree)|os\.(?:remove|unlink|rename))\s*\(\s*(?!['"])""",
        languages=["python"],
    ),
]

# ── SOLIDITY-SPECIFIC ──────────────────────────────────────────────────

SOLIDITY_PATTERNS: list[VulnPattern] = [
    VulnPattern(
        id="SOL-001", cwe="CWE-841", severity="CRITICAL",
        owasp="A04", category="Reentrancy",
        description="Solidity: Potential reentrancy (external call before state update)",
        pattern=r"""\.call\{.*value.*\}\s*\(""",
        languages=["solidity"],
    ),
    VulnPattern(
        id="SOL-002", cwe="CWE-190", severity="HIGH",
        owasp="A04", category="Integer Overflow",
        description="Solidity: Unchecked arithmetic (pre-0.8 pattern without SafeMath)",
        pattern=r"""(?:pragma\s+solidity\s+[<^]?0\.[4-7])""",
        languages=["solidity"],
        false_positive_pattern=r"SafeMath",
    ),
    VulnPattern(
        id="SOL-003", cwe="CWE-284", severity="HIGH",
        owasp="A01", category="Access Control",
        description="Solidity: delegatecall to potentially untrusted contract",
        pattern=r"""\.delegatecall\s*\(""",
        languages=["solidity"],
    ),
    VulnPattern(
        id="SOL-004", cwe="CWE-252", severity="MEDIUM",
        owasp="A04", category="Error Handling",
        description="Solidity: Unchecked return value from external call",
        pattern=r"""(?:\.call|\.send|\.transfer)\s*\([^)]*\)\s*;""",
        languages=["solidity"],
        false_positive_pattern=r"(?:require|assert|bool\s+success)",
    ),
    VulnPattern(
        id="SOL-005", cwe="CWE-330", severity="HIGH",
        owasp="A02", category="Cryptography",
        description="Solidity: block.timestamp used for randomness",
        pattern=r"""block\.(?:timestamp|number|difficulty|prevrandao)\s*[%&|^]""",
        languages=["solidity"],
    ),
]

# ── RUST-SPECIFIC ──────────────────────────────────────────────────────

RUST_PATTERNS: list[VulnPattern] = [
    VulnPattern(
        id="RST-001", cwe="CWE-676", severity="MEDIUM",
        owasp="A04", category="Memory Safety",
        description="Rust: unsafe block usage",
        pattern=r"""\bunsafe\s*\{""",
        languages=["rust"],
    ),
    VulnPattern(
        id="RST-002", cwe="CWE-252", severity="LOW",
        owasp="A04", category="Error Handling",
        description="Rust: unwrap() on potentially fallible operation",
        pattern=r"""\.unwrap\(\)""",
        languages=["rust"],
        false_positive_pattern=r"(?:test|spec|#\[cfg\(test\)\]|#\[test\]|_test\.rs)",
    ),
    VulnPattern(
        id="RST-003", cwe="CWE-78", severity="HIGH",
        owasp="A03", category="Injection",
        description="Rust: Command execution with variable argument",
        pattern=r"""Command::new\s*\(\s*(?!['"])""",
        languages=["rust"],
    ),
]

# ── GENERIC PATTERNS (all languages) ──────────────────────────────────

GENERIC_PATTERNS: list[VulnPattern] = [
    VulnPattern(
        id="GEN-001", cwe="CWE-918", severity="HIGH",
        owasp="A10", category="SSRF",
        description="Server-side request with user-controlled URL",
        pattern=r"""(?:requests\.get|fetch|http\.Get|urllib\.request\.urlopen|axios\.get)\s*\(\s*(?!['"])""",
        languages=["*"],
        false_positive_pattern=r"(?:const|static|CONFIG|BASE_URL|API_URL)",
    ),
    VulnPattern(
        id="GEN-002", cwe="CWE-209", severity="LOW",
        owasp="A05", category="Information Disclosure",
        description="TODO/FIXME related to security",
        pattern=r"""(?:#|//|/\*)\s*(?:TODO|FIXME|HACK|XXX)\s*.*(?:secur|auth|crypt|password|token|vuln|csrf|xss|inject|sanitiz)""",
        languages=["*"],
    ),
    VulnPattern(
        id="GEN-003", cwe="CWE-311", severity="MEDIUM",
        owasp="A02", category="Configuration",
        description="Insecure protocol (http:// for API/auth endpoint)",
        pattern=r"""['"]http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|10\.|192\.168\.|172\.(?:1[6-9]|2[0-9]|3[01]))""",
        languages=["*"],
        false_positive_pattern=r"(?:example|test|mock|placeholder|schema\.org|www\.w3\.org)",
    ),
    VulnPattern(
        id="GEN-004", cwe="CWE-250", severity="MEDIUM",
        owasp="A05", category="Configuration",
        description="Running as root / elevated privileges",
        pattern=r"""(?:USER\s+root|run.*as.*root|chmod\s+777|chmod\s+666|os\.setuid\s*\(\s*0\s*\))""",
        languages=["*"],
    ),
    VulnPattern(
        id="GEN-005", cwe="CWE-1104", severity="LOW",
        owasp="A06", category="Dependencies",
        description="Pinned to wildcard dependency version",
        pattern=r"""['"]\*['"]|['"]latest['"]""",
        languages=["javascript", "typescript"],
        false_positive_pattern=r"(?:peerDependencies|devDependencies.*test)",
    ),
]


# ═══════════════════════════════════════════════════════════════════════
# ALL PATTERNS COMBINED
# ═══════════════════════════════════════════════════════════════════════

ALL_PATTERNS: list[VulnPattern] = (
    SECRET_PATTERNS
    + INJECTION_PATTERNS
    + CRYPTO_PATTERNS
    + AUTH_PATTERNS
    + DESER_PATTERNS
    + CONFIG_PATTERNS
    + PATH_PATTERNS
    + SOLIDITY_PATTERNS
    + RUST_PATTERNS
    + GENERIC_PATTERNS
)


# ═══════════════════════════════════════════════════════════════════════
# SECURITY SCANNER
# ═══════════════════════════════════════════════════════════════════════


class SecurityScanner:
    """Multi-language static application security testing scanner."""

    def __init__(self, patterns: list[VulnPattern] | None = None):
        self.patterns = patterns or ALL_PATTERNS
        # Pre-compile all regexes
        self._compiled: dict[str, re.Pattern] = {}
        self._fp_compiled: dict[str, re.Pattern] = {}
        for pat in self.patterns:
            self._compiled[pat.id] = re.compile(pat.pattern, re.IGNORECASE)
            if pat.false_positive_pattern:
                self._fp_compiled[pat.id] = re.compile(
                    pat.false_positive_pattern, re.IGNORECASE
                )

    def scan_project(
        self, project_path: Path, project_id: str = "", source: str = ""
    ) -> SecurityScanResult:
        """Scan an entire project directory for security vulnerabilities."""
        project_path = Path(project_path)
        if not project_path.exists():
            return SecurityScanResult(project_id=project_id, source=source)

        result = SecurityScanResult(
            project_id=project_id or project_path.name,
            source=source,
        )

        MAX_FILES_PER_PROJECT = 500
        total_lines = 0
        files_scanned = 0

        for file_path in self._iter_source_files(project_path):
            if files_scanned >= MAX_FILES_PER_PROJECT:
                break
            lang = self._detect_language(file_path)
            if lang is None:
                continue

            try:
                content = file_path.read_text(errors="replace")
            except (OSError, PermissionError):
                continue

            if len(content) > MAX_SCAN_SIZE:
                content = content[:MAX_SCAN_SIZE]

            lines = content.splitlines()
            total_lines += len(lines)
            files_scanned += 1

            findings = self._scan_content(content, lines, file_path, lang)
            result.findings.extend(findings)

        result.kloc = total_lines / 1000.0
        result.total_files_scanned = files_scanned

        # Cap per-pattern findings to prevent one noisy rule from dominating
        MAX_PER_PATTERN = 50
        from collections import Counter
        pattern_counts: Counter = Counter()
        capped: list[SecurityFinding] = []
        for f in result.findings:
            pattern_counts[f.pattern_id] += 1
            if pattern_counts[f.pattern_id] <= MAX_PER_PATTERN:
                capped.append(f)
        result.findings = capped

        result.compute_aggregates()
        return result

    def scan_file(self, file_path: Path) -> list[SecurityFinding]:
        """Scan a single file for security vulnerabilities."""
        lang = self._detect_language(file_path)
        if lang is None:
            return []
        try:
            content = file_path.read_text(errors="replace")
        except (OSError, PermissionError):
            return []
        lines = content.splitlines()
        return self._scan_content(content, lines, file_path, lang)

    def _scan_content(
        self,
        content: str,
        lines: list[str],
        file_path: Path,
        language: str,
    ) -> list[SecurityFinding]:
        """Scan file content against all applicable patterns."""
        findings: list[SecurityFinding] = []
        rel_path = str(file_path)

        # Determine applicable patterns
        applicable = [
            p for p in self.patterns
            if "*" in p.languages or language in p.languages
        ]

        for pat in applicable:
            compiled = self._compiled[pat.id]
            fp_compiled = self._fp_compiled.get(pat.id)

            for i, line in enumerate(lines, start=1):
                # Skip comment-only lines for most patterns
                stripped = line.strip()
                if self._is_comment_line(stripped, language):
                    continue

                match = compiled.search(line)
                if match is None:
                    continue

                # Check false positive suppression
                if fp_compiled and fp_compiled.search(line):
                    continue

                # Also check broader context (3 lines before and after)
                context_start = max(0, i - 4)
                context_end = min(len(lines), i + 3)
                context = "\n".join(lines[context_start:context_end])
                if fp_compiled and fp_compiled.search(context):
                    continue

                findings.append(SecurityFinding(
                    pattern_id=pat.id,
                    cwe=pat.cwe,
                    severity=pat.severity,
                    owasp=pat.owasp,
                    category=pat.category,
                    description=pat.description,
                    file_path=rel_path,
                    line_number=i,
                    snippet=stripped[:200],
                    language=language,
                ))

        # Deduplicate: same pattern + same line = 1 finding
        seen = set()
        deduped = []
        for f in findings:
            key = (f.pattern_id, f.file_path, f.line_number)
            if key not in seen:
                seen.add(key)
                deduped.append(f)

        return deduped

    def _iter_source_files(self, project_path: Path):
        """Iterate source files, skipping vendor/build directories."""
        all_exts = set()
        for exts in LANG_EXTENSIONS.values():
            all_exts.update(exts)
        # Also scan config files for secrets
        all_exts.update({".json", ".yaml", ".yml", ".toml", ".env", ".cfg", ".ini"})

        for path in project_path.rglob("*"):
            if path.is_dir():
                continue
            # Skip large files
            try:
                if path.stat().st_size > MAX_SCAN_SIZE:
                    continue
            except OSError:
                continue
            # Skip excluded directories
            parts = path.relative_to(project_path).parts
            if any(p in SKIP_DIRS for p in parts):
                continue
            # Check extension
            if path.suffix.lower() in all_exts:
                yield path

    def _detect_language(self, file_path: Path) -> str | None:
        """Detect programming language from file extension."""
        ext = file_path.suffix.lower()
        for lang, exts in LANG_EXTENSIONS.items():
            if ext in exts:
                return lang
        # Config files get scanned with generic patterns
        if ext in {".json", ".yaml", ".yml", ".toml", ".env", ".cfg", ".ini"}:
            return "config"
        return None

    @staticmethod
    def _is_comment_line(stripped: str, language: str) -> bool:
        """Check if a line is entirely a comment."""
        if not stripped:
            return True
        if language in ("python",):
            return stripped.startswith("#")
        if language in ("javascript", "typescript", "go", "rust"):
            return stripped.startswith("//")
        if language == "solidity":
            return stripped.startswith("//") or stripped.startswith("/*")
        return False


# ═══════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════


def scan_project(project_path: str | Path, **kwargs) -> SecurityScanResult:
    """Convenience function to scan a project."""
    scanner = SecurityScanner()
    return scanner.scan_project(Path(project_path), **kwargs)


def scan_project_summary(project_path: str | Path, **kwargs) -> dict:
    """Scan and return summary dict (for CSV export)."""
    result = scan_project(project_path, **kwargs)
    return {
        "project_id": result.project_id,
        "source": result.source,
        "total_findings": result.total_findings,
        "critical": result.critical,
        "high": result.high,
        "medium": result.medium,
        "low": result.low,
        "kloc": round(result.kloc, 2),
        "files_scanned": result.total_files_scanned,
        "security_debt_density": round(result.security_debt_density, 2),
        "secret_count": result.secret_count,
        "injection_count": result.injection_count,
        "crypto_weakness_count": result.crypto_weakness_count,
        "auth_issue_count": result.auth_issue_count,
        "config_issue_count": result.config_issue_count,
    }


def format_findings_report(result: SecurityScanResult) -> str:
    """Format a human-readable security report."""
    lines = [
        f"Security Scan: {result.project_id}",
        f"{'=' * 60}",
        f"Files scanned: {result.total_files_scanned}",
        f"Code size: {result.kloc:.1f} KLOC",
        f"Total findings: {result.total_findings}",
        f"  CRITICAL: {result.critical}",
        f"  HIGH:     {result.high}",
        f"  MEDIUM:   {result.medium}",
        f"  LOW:      {result.low}",
        f"Security Debt Density: {result.security_debt_density:.2f} findings/KLOC",
        f"",
        f"Category breakdown:",
        f"  Secrets:        {result.secret_count}",
        f"  Injection:      {result.injection_count}",
        f"  Cryptography:   {result.crypto_weakness_count}",
        f"  Authentication: {result.auth_issue_count}",
        f"  Configuration:  {result.config_issue_count}",
        "",
    ]

    if result.findings:
        lines.append("Top findings:")
        lines.append("-" * 60)
        # Sort by severity
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        sorted_findings = sorted(
            result.findings, key=lambda f: severity_order.get(f.severity, 4)
        )
        for f in sorted_findings[:30]:
            lines.append(
                f"  [{f.severity}] {f.pattern_id} ({f.cwe}) {f.description}"
            )
            lines.append(f"    {f.file_path}:{f.line_number}")
            lines.append(f"    > {f.snippet[:100]}")
            lines.append("")

    return "\n".join(lines)
