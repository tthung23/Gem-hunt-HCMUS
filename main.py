import time
import itertools
from pysat.solvers import Glucose3
from pysat.formula import CNF, IDPool
from pysat.card import CardEnc


# 1. Parsing and I/O
def parse_input_file(filename):
    """
    Parse the input file into a 2D list (grid).
    Each cell can be:
      - A known 'T' (trap)
      - A known 'G' (gem)
      - A number (as integer)
      - '_' for unknown
    """
    grid = []
    with open(filename, 'r') as f:
        for line in f:
            # Expecting a line like: "2, _, _, 1, _"
            row_data = [x.strip() for x in line.strip().split(',')]
            parsed_row = []
            for val in row_data:
                if val == '_' or val == '':
                    parsed_row.append('_')
                elif val.upper() == 'T':
                    parsed_row.append('T')
                elif val.upper() == 'G':
                    parsed_row.append('G')
                else:
                    try:
                        parsed_row.append(int(val))
                    except ValueError:
                        parsed_row.append(val)
            grid.append(parsed_row)
    return grid

def write_output_file(filename, grid, stats):
    """
    Write the solved grid to an output file.
    At the end, also save statistics:
      - Number of CNF clauses (if applicable)
      - Number of goals (G)
      - Number of traps (T)
      - Total filled cells (G + T)
      - Time consumed (seconds)
    """
    with open(filename, 'w') as f:
        N = len(grid)
        for i in range(N):
            row_str = [str(cell) for cell in grid[i]]
            f.write(', '.join(row_str) + '\n')
        f.write('\nStatistics:\n')
        f.write("Number of CNF clauses: {}\n".format(stats.get("cnf_clause_count", "N/A")))
        f.write("Number of Goals (G): {}\n".format(stats.get("goal_count", "N/A")))
        f.write("Number of Traps (T): {}\n".format(stats.get("trap_count", "N/A")))
        f.write("Number of Filled cells (G + T): {}\n".format(stats.get("filled_count", "N/A")))
        f.write("Time consumed: {:.4f} seconds\n".format(stats.get("time_consumed", 0)))



# 2. Utility functions
def get_neighbors(r, c, N):
    """
    Return valid neighbor coordinates (up to 8 neighbors) around cell (r, c)
    in an N x N grid.
    """
    neighbors = []
    for nr in [r-1, r, r+1]:
        for nc in [c-1, c, c+1]:
            if 0 <= nr < N and 0 <= nc < N and not (nr == r and nc == c):
                neighbors.append((nr, nc))
    return neighbors

def is_valid_assignment(grid):
    """
    Check if the given grid (candidate solution) satisfies all numeric constraints.
    For every numbered cell, count the traps in its neighbors.
    """
    N = len(grid)
    for i in range(N):
        for j in range(N):
            if isinstance(grid[i][j], int):
                expected = grid[i][j]
                neighbors = get_neighbors(i, j, N)
                count = sum(1 for (r, c) in neighbors if grid[r][c] == 'T')
                if count != expected:
                    return False
    return True


# 3. CNF Generation
def generate_cnf_clauses(grid):
    """
    Generate CNF clauses representing the puzzle constraints.
      - For known T or G cells, fix the variable accordingly.
      - For numbered cells, enforce that the sum of trap variables among its neighbors equals the number.
    Duplicate clauses are removed.
    
    Returns:
      cnf: a CNF object (pysat.formula.CNF) with duplicate-free clauses.
      var_manager: an IDPool mapping each cell to a variable.
    """
    N = len(grid)
    cnf = CNF()
    var_manager = IDPool()

    # Helper: return the variable for cell (i,j)
    def var(i, j):
        return var_manager.id(('x', i, j))
    
    # Use a set to store unique clauses (as sorted tuples)
    clause_set = set()

    # Fix variables for known T/G cells.
    for i in range(N):
        for j in range(N):
            if grid[i][j] == 'T':
                clause_set.add(tuple([var(i, j)]))
            elif grid[i][j] == 'G':
                clause_set.add(tuple([-var(i, j)]))
    
    # For numbered cells, enforce: exactly n of the neighbors are traps.
    for i in range(N):
        for j in range(N):
            if isinstance(grid[i][j], int):
                n = grid[i][j]
                neighs = get_neighbors(i, j, N)
                neighbor_vars = [var(r, c) for (r, c) in neighs]
                # Use CardEnc to encode "at most n" and "at least n" constraints.
                atmost_n = CardEnc.atmost(lits=neighbor_vars, bound=n, vpool=var_manager, encoding=1)
                atleast_n = CardEnc.atleast(lits=neighbor_vars, bound=n, vpool=var_manager, encoding=1)
                for clause in atmost_n.clauses:
                    clause_set.add(tuple(sorted(clause)))
                for clause in atleast_n.clauses:
                    clause_set.add(tuple(sorted(clause)))
    
    # Convert the set of unique clause tuples back to lists and assign to cnf
    cnf.clauses = [list(clause) for clause in clause_set]
    return cnf, var_manager


# 4. PySAT
def solve_with_pysat(grid):
    """
    Solve the puzzle using PySAT. Returns a tuple:
      (solved_grid, stats)
    where stats is a dictionary containing:
      - cnf_clause_count: number of clauses generated
      - goal_count: number of cells with 'G'
      - trap_count: number of cells with 'T'
      - filled_count: total number of cells assigned (G + T)
      - time_consumed: total time in seconds
    Numeric clue cells are preserved.
    """
    start_time = time.time()
    cnf, var_manager = generate_cnf_clauses(grid)
    clause_count = len(cnf.clauses)
    solver = Glucose3()
    for clause in cnf.clauses:
        solver.add_clause(clause)

    if not solver.solve():
        print("No solution found by PySAT.")
        return None, {"cnf_clause_count": clause_count}

    model = solver.get_model()
    model_set = set(model)
    N = len(grid)
    solved_grid = [row[:] for row in grid]  # make a copy

    def var(i, j):
        return var_manager.id(('x', i, j))

    # Only update unknown cells ('_'); leave numeric clues unchanged.
    for i in range(N):
        for j in range(N):
            if solved_grid[i][j] == '_':
                if var(i, j) in model_set:
                    solved_grid[i][j] = 'T'
                else:
                    solved_grid[i][j] = 'G'

    end_time = time.time()
    time_consumed = end_time - start_time

    # Count stats: T = traps, G = goals, filled = total non-unknown.
    trap_count = 0
    goal_count = 0
    filled_count = 0
    for i in range(N):
        for j in range(N):
            if solved_grid[i][j] == 'T':
                trap_count += 1
                filled_count += 1
            elif solved_grid[i][j] == 'G':
                goal_count += 1
                filled_count += 1

    stats = {
        "cnf_clause_count": clause_count,
        "goal_count": goal_count,
        "trap_count": trap_count,
        "filled_count": filled_count,
        "time_consumed": time_consumed
    }
    return solved_grid, stats


# 5. Brute Force
def solve_with_brute_force(grid):
    """
    Brute force approach:
      - For every unknown cell, try assigning 'T' or 'G'.
      - Return immediately when a valid assignment is found.
    Returns a tuple (solved_grid, stats) where stats includes:
      - trap_count, goal_count, filled_count, and time_consumed.
      - 'cnf_clause_count' is not applicable here ("N/A").
    """
    start_time = time.time()
    N = len(grid)
    unknowns = [(i, j) for i in range(N) for j in range(N) if grid[i][j] == '_']

    for assignment in itertools.product([True, False], repeat=len(unknowns)):
        candidate = [row[:] for row in grid]
        for idx, (i, j) in enumerate(unknowns):
            candidate[i][j] = 'T' if assignment[idx] else 'G'
        if is_valid_assignment(candidate):
            trap_count = sum(row.count('T') for row in candidate)
            goal_count = sum(row.count('G') for row in candidate)
            time_consumed = time.time() - start_time
            return candidate, {
                "cnf_clause_count": "N/A",
                "trap_count": trap_count,
                "goal_count": goal_count,
                "filled_count": trap_count + goal_count,
                "time_consumed": time_consumed
            }
    return None, {}


# 6. Backtracking
def is_partial_consistent(candidate, r, c):
    """
    Check local consistency around the cell (r, c). For every numbered cell adjacent 
    to (r, c), if all its neighbors are assigned, the count of traps must match the number.
    Even if not all assigned, the count should not exceed the clue.
    """
    N = len(candidate)
    # Check each cell in the neighborhood of (r,c) that is a number
    for i in range(max(0, r-1), min(N, r+2)):
        for j in range(max(0, c-1), min(N, c+2)):
            if isinstance(candidate[i][j], int):
                expected = candidate[i][j]
                neighbors = get_neighbors(i, j, N)
                count = 0
                all_assigned = True
                for (nr, nc) in neighbors:
                    if candidate[nr][nc] == 'T':
                        count += 1
                    elif candidate[nr][nc] == '_':
                        all_assigned = False
                if count > expected:
                    return False
                if all_assigned and count != expected:
                    return False
    return True

def solve_with_backtracking(grid):
    """
    Backtracking approach:
      - Recursively assign 'T' or 'G' to unknown cells.
      - Use partial consistency checking to prune invalid branches.
      - Stop immediately when a valid solution is found.
    Returns a tuple (solved_grid, stats) where stats includes:
      - trap_count, goal_count, filled_count, and time_consumed.
      - 'cnf_clause_count' is not applicable here ("N/A").
    """
    start_time = time.time()
    N = len(grid)
    unknowns = [(i, j) for i in range(N) for j in range(N) if grid[i][j] == '_']

    def backtrack(index, candidate):
        if index == len(unknowns):
            # Final check: The complete assignment must satisfy all numeric constraints.
            if is_valid_assignment(candidate):
                return candidate
            return None

        i, j = unknowns[index]
        for val in ['T', 'G']:
            candidate[i][j] = val
            # Check local consistency for this assignment:
            if is_partial_consistent(candidate, i, j):
                result = backtrack(index + 1, candidate)
                if result:
                    return result
            candidate[i][j] = '_'
        return None

    candidate = [row[:] for row in grid]
    result = backtrack(0, candidate)
    if result:
        trap_count = sum(row.count('T') for row in result)
        goal_count = sum(row.count('G') for row in result)
        time_consumed = time.time() - start_time
        return result, {
            "cnf_clause_count": "N/A",
            "trap_count": trap_count,
            "goal_count": goal_count,
            "filled_count": trap_count + goal_count,
            "time_consumed": time_consumed
        }
    return None, {}



# 7. Main menu and user interaction
def main():
    while True:
        print("\n=== GEM HUNTER PUZZLE ===")
        print("1) Solve using PySAT")
        print("2) Solve using Brute Force")
        print("3) Solve using Backtracking")
        print("4) Exit")
        choice = input("Choose an option: ").strip()

        if choice not in ['1', '2', '3', '4']:
            print("Invalid choice. Try again.")
            continue
        if choice == '4':
            print("Exiting...")
            break

        input_file = input("Enter input file path: ").strip()
        grid = parse_input_file(input_file)

        if choice == '1':
            solved, stats = solve_with_pysat(grid)
            algo_name = "pysat"
        elif choice == '2':
            solved, stats = solve_with_brute_force(grid)
            algo_name = "bruteforce"
        else:
            solved, stats = solve_with_backtracking(grid)
            algo_name = "backtracking"

        if solved is None:
            print("No solution found or puzzle unsolvable.")
        else:
            print("Solution:")
            for row in solved:
                print(row)
            print("\nStatistics:")
            for key, value in stats.items():
                if key == "time_consumed":
                    print(f"{key}: {value:.4f} seconds")
                else:
                    print(f"{key}: {value}")

            output_file = input("\nEnter output file path to save solution and stats: ").strip()
            write_output_file(output_file, solved, stats)
            print(f"Solution and statistics written to {output_file}.")

if __name__ == "__main__":
    main()
