# Template: Quality Gate Plugin

```python
"""
Quality Gate Plugin Template
Copy and modify for new gate implementations.
"""

import subprocess
import re
import time
from typing import List, Optional

from gate_types import GateConfig, GateResult, GateStatus, GateLevel, Issue
from gate_plugin import GatePlugin


class MyPlugin(GatePlugin):
    """My custom gate plugin"""
    
    def execute(self, files: List[str], working_dir: str) -> GateResult:
        """Execute the gate check"""
        start_time = time.time()
        
        try:
            # Build command
            command = f"my-tool check {' '.join(files)}"
            result = self._run_command(command, working_dir)
            
            duration = time.time() - start_time
            
            # Parse issues from output
            issues = self._parse_output(result.stdout)
            
            # Create result
            if result.returncode == 0:
                gate_result = self._create_success_result(
                    message="Check passed",
                    output=result.stdout
                )
            else:
                gate_result = self._create_failure_result(
                    message=f"Found {len(issues)} issues",
                    output=result.stdout,
                    issues=issues
                )
            
            gate_result.duration = duration
            return gate_result
            
        except Exception as e:
            return self._create_error_result(message=str(e))
    
    def is_available(self) -> bool:
        """Check if tool is installed"""
        return self._check_tool_available("my-tool")
    
    def get_version(self) -> Optional[str]:
        """Get tool version"""
        try:
            result = self._run_command("my-tool --version", ".")
            return result.stdout.strip()
        except:
            return None
    
    def _parse_output(self, output: str) -> List[Issue]:
        """Parse tool output into Issue objects"""
        issues = []
        # Example: file.py:10:5: ERROR message
        pattern = r'^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+): (?P<msg>.+)$'
        for match in re.finditer(pattern, output, re.MULTILINE):
            issues.append(Issue(
                severity="error",
                message=match.group("msg"),
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("col")),
            ))
        return issues


# Register in gate_plugins.py:
# GATE_PLUGINS["my-tool"] = MyPlugin
```

# Template: MCP Server Tool

```python
"""
MCP Server Tool Template
Add new tools to mcp_server.py following this pattern.
"""

def my_new_tool(param1: str, param2: int = 0) -> dict:
    """
    Tool description
    
    Args:
        param1: Description
        param2: Description
    
    Returns:
        dict: Result description
    """
    start_time = time.time()
    
    try:
        # Implementation
        result = do_something(param1, param2)
        
        output = {
            "key": "value",
            "count": len(result),
        }
        
        duration = time.time() - start_time
        audit_logger.log("my_new_tool", {
            "param1": param1,
            "param2": param2,
        }, output, "success", duration)
        
        return output
        
    except Exception as e:
        duration = time.time() - start_time
        audit_logger.log("my_new_tool", {
            "param1": param1,
        }, {"error": str(e)}, "error", duration)
        raise WorkflowError(f"Tool failed: {str(e)}")
```
