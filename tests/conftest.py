"""Pytest configuration and fixtures for aicoder-debt tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Generator

import pytest

from aicoder_debt.constants import DeploymentRating, EdgeType
from aicoder_debt.models import Cycle, DDGAnalysis, DDGEdge, DDGNode, DDGStatistics


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def python_project(temp_dir: Path) -> Path:
    """Create a simple Python project fixture."""
    # Create main module
    (temp_dir / "main.py").write_text(
        """
import os
from utils import helper

def main():
    api_key = os.environ.get("API_KEY")
    result = helper.process_data()
    return result

if __name__ == "__main__":
    main()
"""
    )

    # Create utils module
    (temp_dir / "utils").mkdir()
    (temp_dir / "utils" / "__init__.py").write_text("")
    (temp_dir / "utils" / "helper.py").write_text(
        """
def process_data():
    return {"status": "ok"}
"""
    )

    # Create .env file
    (temp_dir / ".env").write_text(
        """
API_KEY=test123
DATABASE_URL=postgres://localhost/test
"""
    )

    # Create requirements.txt
    (temp_dir / "requirements.txt").write_text(
        """
requests>=2.28
pydantic>=2.0
fake-nonexistent-package>=1.0
"""
    )

    return temp_dir


@pytest.fixture
def solidity_project(temp_dir: Path) -> Path:
    """Create a simple Solidity project fixture."""
    # Create contracts directory
    (temp_dir / "contracts").mkdir()

    # Token contract
    (temp_dir / "contracts" / "Token.sol").write_text(
        """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Token {
    string public name;
    mapping(address => uint256) public balances;

    constructor(string memory _name) {
        name = _name;
    }

    function transfer(address to, uint256 amount) public {
        balances[msg.sender] -= amount;
        balances[to] += amount;
    }
}
"""
    )

    # Exchange contract that depends on Token
    (temp_dir / "contracts" / "Exchange.sol").write_text(
        """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./Token.sol";

contract Exchange {
    Token public token;

    constructor(address tokenAddress) {
        token = Token(tokenAddress);
    }

    function swap(uint256 amount) public {
        token.transfer(msg.sender, amount);
    }
}
"""
    )

    return temp_dir


@pytest.fixture
def docker_project(temp_dir: Path) -> Path:
    """Create a Docker Compose project fixture."""
    # Create docker-compose.yml
    (temp_dir / "docker-compose.yml").write_text(
        """
version: "3.8"

services:
  api:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgres://db:5432/app
      - REDIS_URL=redis://cache:6379
    depends_on:
      - db
      - cache

  db:
    image: postgres:14
    environment:
      - POSTGRES_DB=app
      - POSTGRES_PASSWORD=secret

  cache:
    image: redis:7

  worker:
    build: ./worker
    environment:
      - DATABASE_URL=postgres://db:5432/app
    depends_on:
      db:
        condition: service_healthy
"""
    )

    return temp_dir


@pytest.fixture
def mixed_project(temp_dir: Path) -> Path:
    """Create a mixed project with Python and Docker."""
    # Create main module
    (temp_dir / "main.py").write_text(
        """
import os
from utils import helper

def main():
    api_key = os.environ.get("API_KEY")
    result = helper.process_data()
    return result
"""
    )

    # Create utils module
    (temp_dir / "utils").mkdir()
    (temp_dir / "utils" / "__init__.py").write_text("")
    (temp_dir / "utils" / "helper.py").write_text(
        """
def process_data():
    return {"status": "ok"}
"""
    )

    # Create .env file
    (temp_dir / ".env").write_text("API_KEY=test123\n")

    # Add docker-compose.yml
    (temp_dir / "docker-compose.yml").write_text(
        """
version: "3.8"

services:
  app:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - db

  db:
    image: postgres:14
"""
    )

    return temp_dir


@pytest.fixture
def simple_ddg() -> DDGAnalysis:
    """Create a simple DDG with no cycles."""
    nodes = [
        DDGNode(id="a", name="A", type="service"),
        DDGNode(id="b", name="B", type="database"),
    ]
    edges = [
        DDGEdge(
            source="a",
            target="b",
            edge_type=EdgeType.STATE,
        )
    ]
    return DDGAnalysis(
        nodes=nodes,
        edges=edges,
        cycles=[],
        statistics=DDGStatistics(
            total_nodes=2,
            total_edges=1,
            state_edges=1,
        ),
    )


@pytest.fixture
def cyclic_ddg() -> DDGAnalysis:
    """Create a DDG with a cycle."""
    nodes = [
        DDGNode(id="a", name="A", type="service"),
        DDGNode(id="b", name="B", type="service"),
    ]
    edges = [
        DDGEdge(source="a", target="b", edge_type=EdgeType.ADDR),
        DDGEdge(source="b", target="a", edge_type=EdgeType.ADDR),
    ]
    cycles = [
        Cycle(
            nodes=["a", "b"],
            edges=edges,
            has_state_edge=False,
            is_irreparable=False,
        )
    ]
    return DDGAnalysis(
        nodes=nodes,
        edges=edges,
        cycles=cycles,
        statistics=DDGStatistics(
            total_nodes=2,
            total_edges=2,
            addr_edges=2,
            total_cycles=1,
        ),
    )


@pytest.fixture
def stateful_cyclic_ddg() -> DDGAnalysis:
    """Create a DDG with a stateful cycle (repairable)."""
    nodes = [
        DDGNode(id="a", name="A", type="service"),
        DDGNode(id="b", name="B", type="service"),
    ]
    edges = [
        DDGEdge(source="a", target="b", edge_type=EdgeType.STATE),
        DDGEdge(source="b", target="a", edge_type=EdgeType.ADDR),
    ]
    cycles = [
        Cycle(
            nodes=["a", "b"],
            edges=edges,
            has_state_edge=True,
            is_irreparable=False,
        )
    ]
    return DDGAnalysis(
        nodes=nodes,
        edges=edges,
        cycles=cycles,
        statistics=DDGStatistics(
            total_nodes=2,
            total_edges=2,
            addr_edges=1,
            state_edges=1,
            total_cycles=1,
            stateful_cycles=1,
        ),
    )


@pytest.fixture
def irreparable_ddg() -> DDGAnalysis:
    """Create a DDG with an irreparable cycle."""
    nodes = [
        DDGNode(id="a", name="A", type="contract"),
        DDGNode(id="b", name="B", type="contract"),
    ]
    edges = [
        DDGEdge(
            source="a",
            target="b",
            edge_type=EdgeType.STATE,
            requires_atomicity=True,
        ),
        DDGEdge(
            source="b",
            target="a",
            edge_type=EdgeType.STATE,
            requires_atomicity=True,
        ),
    ]
    cycles = [
        Cycle(
            nodes=["a", "b"],
            edges=edges,
            has_state_edge=True,
            is_irreparable=True,
        )
    ]
    return DDGAnalysis(
        nodes=nodes,
        edges=edges,
        cycles=cycles,
        statistics=DDGStatistics(
            total_nodes=2,
            total_edges=2,
            state_edges=2,
            total_cycles=1,
            stateful_cycles=1,
            irreparable_cycles=1,
        ),
    )
