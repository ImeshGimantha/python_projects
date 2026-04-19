import json
import sys
from pathlib import Path
from datetime import datetime
from argparse import ArgumentParser
from inspect import signature
from typing import (
    TypeAlias,
    TypedDict,
    Literal,
    Callable,
    get_args,
    get_origin,
    Union,
    Annotated,
    Optional
)

supported_queries: dict[str, dict] = {}
TaskStatus: TypeAlias = Literal["done", "in-progress", "todo"]
DatabaseRow = TypedDict(
    "DatabaseRow",
    {"description": str, "status": TaskStatus, "created_At": str, "updated_At": str}
)
Database: TypeAlias = dict[str, DatabaseRow]

def main() -> None:
    query, args, db_path = parse_args()
    database: Database = load_database(db_path)
    try:
        query(database, **args)
    except Exception as e:
        sys.exit(str(e))
    save_database(database, db_path)


def load_database(path: Path) -> Database:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_database(database: Database, path: Path):
    with open(path, "w") as f:
        json.dump(database, f, indent=4, sort_keys=True, ensure_ascii=False)


def parse_args() -> tuple[Callable, dict, Path]:
    parser = ArgumentParser(prog="task", description="A CLI application for efficiently manage your tasks")
    parser.add_argument("--db", help="Path to the database file (default: ./task.json)", default="./task.json")
    subparsers = parser.add_subparsers(title="commands", dest="command", required=True)
    
    for name, properties in supported_queries.items():
        p = subparsers.add_parser(name, help=properties["help"])
        for arg in properties["args"]:
            name_or_flags = arg.pop("name_or_flags")
            p.add_argument(*name_or_flags, **arg)
            arg["name_or_flags"] = name_or_flags

    args: dict = vars(parser.parse_args())
    query: Callable = supported_queries[args.pop("command")]["target"]
    db_path: Path = Path(args.pop("db")).expanduser().resolve()
    
    if db_path.is_dir():
        parser.error(f"Database path '{db_path}' is a directory")

    return query, args, db_path


def add_query(func: Callable) -> Callable:
    """Decorator to add a query to the supported query dictionary."""
    name = func.__name__.removesuffix("_task").replace("_", "-")

    supported_queries[name] = {
        "target": func,
        "help": func.__doc__,
        "args": []
    }

    args = supported_queries[name]["args"]

    for param in signature(func).parameters.values():
        if param.name == "database": continue
        type, *metadata = get_args(param.annotation)
        if get_origin(type) is Union:
            type = get_args(type)[0]
        
        args.append(
            {
                "name_or_flags": metadata[1:] if len(metadata) > 1 else [param.name],
                "help": metadata[0],
                "choices": get_args(type) if get_origin(type) is Literal else None,
                "default": param.default if param.default is not param.empty else None
            }
        )

    return func


@add_query
def add_task(
    database: Database,
    description: Annotated[str, "Description of the task"]
) -> None:
    task_id: str = str(max(map(int, database.keys()), default=0) + 1)
    today: str = datetime.today().isoformat(timespec="seconds")
    database[task_id] = {
        "description": description,
        "status": "todo",
        "created_At": today,
        "updated_At": today
    }

    print_table(database, task_id)


@add_query
def list_task(database: Database) -> None:
    print_table(database)
    

def print_table(database: Database, task_id="0") -> None:
    dashed_border = "+-----------+-------------------------+------------+"

    print(dashed_border)
    print("|  Task ID  |       Description       |   Status   |")
    print(dashed_border)

    for task in database.keys():
        check_id = task if task_id == "0" else task_id
        print(f"|{int(check_id):6d}     |     {database[check_id]["description"]:<20}|    {database[check_id]["status"]:<8}|")
        print(dashed_border)
        if check_id == task_id: break


@add_query
def update_task(
    database: Database,
    id: Annotated[str, "Id of the task you want to update"],
    description: Annotated[Optional[str], "New description for the task", "--description", "-d"] = None,
    status: Annotated[Optional[TaskStatus], "New status for the task", "--status", "-s"] = None
) -> None:
    """Update the description or status of a task"""
    if id not in database:
        raise KeyError(f"No task found with ID '{id}'")
    if description is not None:
        database[id]["description"] = description
    if status is not None:
        if status not in (valid := get_args(TaskStatus)):
            raise ValueError(f"Invalid status '{status}'. Valid status are: {', '.join(valid)}")
        database[id]["status"] = status
    database[id]["updated_At"] = datetime.today().isoformat(timespec="seconds")

    print_table(database, id)

if __name__ == "__main__":
    main()