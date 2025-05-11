from re import compile

def clean_log(log: str) -> str:
    """
    Remove ANSI escape codes and unnecessary whitespace from the log.
    """
    # Regex to match ANSI escape codes
    ansi_escape = compile(r'(?:\x1B[@-Z\\-_]|\x1B\[[0-?]*[ -/]*[@-~])')
    # Remove ANSI codes and strip extra whitespace
    clean_line = ansi_escape.sub('', log).strip()
    return clean_line