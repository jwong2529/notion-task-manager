RESET = "\033[0m"
BOLD = "\033[1m"

FG_BLUE = "\033[94m"
FG_GREEN = "\033[92m"
FG_YELLOW = "\033[93m"
FG_RED = "\033[91m"
FG_GRAY = "\033[90m"

def h(text):      # headers
    return f"{BOLD}{FG_BLUE}{text}{RESET}"

def ok(text):     # success
    return f"{FG_GREEN}{text}{RESET}"

def warn(text):   # warnings
    return f"{FG_YELLOW}{text}{RESET}"

def err(text):    # errors
    return f"{FG_RED}{text}{RESET}"

def dim(text):    # secondary text
    return f"{FG_GRAY}{text}{RESET}"
