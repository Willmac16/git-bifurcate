#!/bin/bash
set -e

python3 -c "from file1 import func1; assert func1() == 'file1', 'file1 failed'"
python3 -c "from file2 import func2; assert func2() == 'file2', 'file2 failed'"
python3 -c "from file3 import func3; assert func3() == 'file3', 'file3 failed'"
python3 -c "from file4 import func4; assert func4() == 'file4', 'file4 failed'"
python3 -c "from file5 import func5; assert func5() == 'file5', 'file5 failed'"

echo "All tests passed!"
