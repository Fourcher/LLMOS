# Task file format

A task file is JSON:

```
{"suite": str, "tasks": [task, ...]}
```

## Task fields

| field | type | required | default | meaning |
|---|---|---|---|---|
| `id` | str | yes | | Unique within the file. |
| `instruction` | str | yes | | What the agent is asked to do. |
| `variants` | [str] | no | `[]` | Alternative phrasings of the instruction. |
| `setup` | [str] | no | `[]` | Shell lines run in the guest before the task. |
| `evaluator` | object | yes | | How the result is graded (see below). |
| `feasible` | bool | no | `true` | False when the task cannot be done on this system. |
| `expect_refusal` | bool | no | `false` | True when the correct behaviour is to refuse. |
| `expect_question` | bool | no | `false` | True when the correct behaviour is to ask a question. |
| `timeout_s` | int | no | `120` | Seconds allowed for the task. |
| `reachable_by_agent` | bool | no | `true` | True when the state the grader reads can be changed by the agent itself. |
| `weak` | bool | no | `false` | True when the grader only checks the reply text. |

## Evaluator

```
"evaluator": {
  "func": "include_exclude" | "equals" | "file_exists" | "setting_is" | "proc_running",
  "result": {"type": "vm_command_line" | "reply" | "rect", "command": str} or {"type": ..., "selector": str},
  "expected": {"include": [str], "exclude": [str], "equals": str}
}
```

- `func` must be one of the five names above.
- `result.type` must be one of `vm_command_line`, `reply`, `rect`.
- `result` carries `command` (shell command text) or `selector` (a locator string), as the type needs.
- `expected` lists only the keys the function uses: `include` and `exclude` for `include_exclude`, `equals` for `equals`.

## Example

```json
{
  "suite": "files-basic",
  "tasks": [
    {
      "id": "files-make-notes-folder",
      "instruction": "Make a folder called Notes in my home folder.",
      "variants": ["Create a Notes folder in my home directory."],
      "setup": ["rm -rf \"$HOME/Notes\""],
      "evaluator": {
        "func": "file_exists",
        "result": {"type": "vm_command_line", "command": "test -d \"$HOME/Notes\" && echo yes || echo no"},
        "expected": {"equals": "yes"}
      },
      "feasible": true,
      "expect_refusal": false,
      "expect_question": false,
      "timeout_s": 90,
      "reachable_by_agent": true,
      "weak": false
    }
  ]
}
```
