#!/bin/bash
set -e

python3 -c "from module1 import value1; assert value1 >= 1"
python3 -c "from module2 import value2; assert value2 == 2"
python3 -c "from module3 import value3; assert value3 >= 3"
python3 -c "from module4 import value4; assert value4 >= 4"

echo "All tests passed!"
