from __future__ import annotations

import re
from typing import Any

from learn_core.text_utils import normalize_string_list


def build_algorithm_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "c1", "category": "concept", "type": "single",
            "question": "在算法分析里，通常用什么方式描述输入规模足够大时的渐进增长趋势？",
            "options": ["Big-O 记号", "Markdown 记号", "ASCII 记号", "HTTP 状态码"],
            "answer": 0,
            "explanation": "Big-O 用来描述增长趋势，是算法复杂度分析中的常用工具。",
            "tags": ["复杂度", "基础概念"],
        },
        {
            "id": "c2", "category": "concept", "type": "multi",
            "question": "下面哪些数据结构常用于加速查找或去重？",
            "options": ["哈希表", "集合", "数组顺序扫描", "平衡搜索树"],
            "answer": [0, 1, 3],
            "explanation": "哈希表、集合、平衡搜索树都可以用于高效查找；单纯顺序扫描通常更慢。",
            "tags": ["数据结构"],
        },
        {
            "id": "c3", "category": "concept", "type": "judge",
            "question": "二分查找只适用于有序序列。",
            "answer": True,
            "explanation": "二分查找依赖有序性，否则无法依据中点结果缩小区间。",
            "tags": ["二分查找"],
        },
        {
            "id": "c4", "category": "concept", "type": "single",
            "question": "如果一个问题天然能拆成若干相似子问题，并且子问题之间互不依赖，最常见的思路是什么？",
            "options": ["递归 / 分治", "直接忽略边界", "只打印调试信息", "固定返回 0"],
            "answer": 0,
            "explanation": "递归和分治常用于把大问题拆成结构相似的小问题。",
            "tags": ["递归", "分治"],
        },
        {
            "id": "c5", "category": "concept", "type": "multi",
            "question": "关于双指针技巧，下面哪些说法更常见？",
            "options": ["常用于数组和字符串", "经常配合有序条件", "只适用于树结构", "可用于滑动窗口问题"],
            "answer": [0, 1, 3],
            "explanation": "双指针常见于数组、字符串、滑动窗口等场景，不只限于树。",
            "tags": ["双指针"],
        },
        {
            "id": "c6", "category": "concept", "type": "judge",
            "question": "动态规划通常要求你先明确状态、状态转移和边界条件。",
            "answer": True,
            "explanation": "这三部分是动态规划建模的核心。",
            "tags": ["动态规划"],
        },
        {
            "id": "c7", "category": "concept", "type": "single",
            "question": "遍历图时，如果你想按层扩展节点，通常优先考虑哪种方法？",
            "options": ["BFS", "DFS", "排序", "哈希"],
            "answer": 0,
            "explanation": "BFS 天然按层推进。",
            "tags": ["图", "BFS"],
        },
    ]

    code = [
        make_code_question("code1", "easy", "数组求和", "sum_list", ["nums"],
                           "请实现函数 sum_list(nums)，返回整数列表的元素和。",
                           "def sum_list(nums):\n    pass",
                           "def sum_list(nums):\n    return sum(nums)",
                           [
                               {"input": [[1, 2, 3]], "expected": 6},
                               {"input": [[0, 0]], "expected": 0},
                               {"input": [[-1, 1]], "expected": 0},
                           ], ["数组", "遍历"]),
        make_code_question("code2", "easy", "查找最大值", "max_value", ["nums"],
                           "请实现函数 max_value(nums)，返回列表中的最大值。",
                           "def max_value(nums):\n    pass",
                           "def max_value(nums):\n    return max(nums)",
                           [
                               {"input": [[3, 1, 5]], "expected": 5},
                               {"input": [[-3, -7]], "expected": -3},
                               {"input": [[8]], "expected": 8},
                           ], ["数组"]),
        make_code_question("code3", "medium", "判断回文串", "is_palindrome", ["s"],
                           "请实现函数 is_palindrome(s)，判断字符串是否为回文串。",
                           "def is_palindrome(s):\n    pass",
                           "def is_palindrome(s):\n    return s == s[::-1]",
                           [
                               {"input": ["level"], "expected": True},
                               {"input": ["algo"], "expected": False},
                               {"input": ["a"], "expected": True},
                           ], ["字符串", "双指针"]),
        make_code_question("code4", "medium", "二分查找", "binary_search", ["nums", "target"],
                           "请实现函数 binary_search(nums, target)，若 target 存在则返回其下标，否则返回 -1。nums 保证有序。",
                           "def binary_search(nums, target):\n    pass",
                           "def binary_search(nums, target):\n    left, right = 0, len(nums) - 1\n    while left <= right:\n        mid = (left + right) // 2\n        if nums[mid] == target:\n            return mid\n        if nums[mid] < target:\n            left = mid + 1\n        else:\n            right = mid - 1\n    return -1",
                           [
                               {"input": [[1, 3, 5, 7], 5], "expected": 2},
                               {"input": [[2, 4, 6], 1], "expected": -1},
                               {"input": [[9], 9], "expected": 0},
                           ], ["二分查找"]),
        make_code_question("code5", "medium", "统计唯一元素", "count_unique", ["nums"],
                           "请实现函数 count_unique(nums)，返回列表中不同元素的个数。",
                           "def count_unique(nums):\n    pass",
                           "def count_unique(nums):\n    return len(set(nums))",
                           [
                               {"input": [[1, 1, 2, 3]], "expected": 3},
                               {"input": [[5, 5, 5]], "expected": 1},
                               {"input": [[]], "expected": 0},
                           ], ["哈希", "去重"]),
        make_code_question("code6", "medium", "括号有效性", "is_valid_parentheses", ["s"],
                           "请实现函数 is_valid_parentheses(s)，判断括号字符串是否有效。只包含 ()[]{}。",
                           "def is_valid_parentheses(s):\n    pass",
                           "def is_valid_parentheses(s):\n    pairs = {')': '(', ']': '[', '}': '{'}\n    stack = []\n    for ch in s:\n        if ch in '([{':\n            stack.append(ch)\n        else:\n            if not stack or stack.pop() != pairs[ch]:\n                return False\n    return not stack",
                           [
                               {"input": ["()[]{}"], "expected": True},
                               {"input": ["(]"], "expected": False},
                               {"input": ["([{}])"], "expected": True},
                           ], ["栈"]),
        make_code_question("code7", "project", "两数之和", "two_sum", ["nums", "target"],
                           "请实现函数 two_sum(nums, target)，返回和为 target 的两个下标。保证存在唯一答案。",
                           "def two_sum(nums, target):\n    pass",
                           "def two_sum(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n        if target - n in seen:\n            return [seen[target - n], i]\n        seen[n] = i",
                           [
                               {"input": [[2, 7, 11, 15], 9], "expected": [0, 1]},
                               {"input": [[3, 2, 4], 6], "expected": [1, 2]},
                               {"input": [[3, 3], 6], "expected": [0, 1]},
                           ], ["哈希", "经典题"]),
    ]
    return concept, code


def build_math_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "c1", "category": "concept", "type": "single",
            "question": "如果两个事件互斥，那么它们可以同时发生吗？",
            "options": ["可以", "不可以", "只在样本很大时可以", "取决于是否独立"],
            "answer": 1,
            "explanation": "互斥表示不能同时发生。",
            "tags": ["概率"],
        },
        {
            "id": "c2", "category": "concept", "type": "multi",
            "question": "下面哪些量能衡量一组数据的集中趋势？",
            "options": ["平均数", "中位数", "众数", "极差"],
            "answer": [0, 1, 2],
            "explanation": "平均数、中位数、众数都描述集中趋势；极差更偏离散程度。",
            "tags": ["统计"],
        },
        {
            "id": "c3", "category": "concept", "type": "judge",
            "question": "如果函数在某点处可导，那么它在该点一定连续。",
            "answer": True,
            "explanation": "可导蕴含连续。",
            "tags": ["微积分"],
        },
        {
            "id": "c4", "category": "concept", "type": "single",
            "question": "在线性代数里，矩阵乘法一般要求什么条件？",
            "options": ["两个矩阵行数相等", "两个矩阵列数相等", "前一个矩阵列数等于后一个矩阵行数", "两个矩阵完全同型"],
            "answer": 2,
            "explanation": "矩阵乘法要求前者列数等于后者行数。",
            "tags": ["线性代数"],
        },
        {
            "id": "c5", "category": "concept", "type": "multi",
            "question": "下面哪些属于常见离散数学对象？",
            "options": ["集合", "命题", "图", "导数"],
            "answer": [0, 1, 2],
            "explanation": "集合、命题、图都属于离散数学常见对象。",
            "tags": ["离散数学"],
        },
        {
            "id": "c6", "category": "concept", "type": "judge",
            "question": "标准差越大，通常表示数据波动越大。",
            "answer": True,
            "explanation": "标准差刻画离散程度。",
            "tags": ["统计"],
        },
        {
            "id": "c7", "category": "concept", "type": "single",
            "question": "若命题“如果 A 则 B”为真，而 A 为真，那么根据哪种推理可得 B 为真？",
            "options": ["归纳法", "反证法", "肯定前件", "枚举法"],
            "answer": 2,
            "explanation": "这对应常见的肯定前件推理。",
            "tags": ["逻辑"],
        },
    ]

    code = [
        make_code_question("code1", "easy", "计算平均数", "mean_value", ["nums"],
                           "请实现函数 mean_value(nums)，返回列表平均数。保证 nums 非空。",
                           "def mean_value(nums):\n    pass",
                           "def mean_value(nums):\n    return sum(nums) / len(nums)",
                           [
                               {"input": [[1, 2, 3]], "expected": 2.0},
                               {"input": [[5, 5]], "expected": 5.0},
                               {"input": [[-2, 2]], "expected": 0.0},
                           ], ["统计"]),
        make_code_question("code2", "easy", "最大公约数", "gcd_value", ["a", "b"],
                           "请实现函数 gcd_value(a, b)，返回两个正整数的最大公约数。",
                           "def gcd_value(a, b):\n    pass",
                           "def gcd_value(a, b):\n    while b:\n        a, b = b, a % b\n    return a",
                           [
                               {"input": [12, 18], "expected": 6},
                               {"input": [7, 3], "expected": 1},
                               {"input": [9, 6], "expected": 3},
                           ], ["数论"]),
        make_code_question("code3", "medium", "判断素数", "is_prime", ["n"],
                           "请实现函数 is_prime(n)，判断 n 是否是素数。",
                           "def is_prime(n):\n    pass",
                           "def is_prime(n):\n    if n < 2:\n        return False\n    i = 2\n    while i * i <= n:\n        if n % i == 0:\n            return False\n        i += 1\n    return True",
                           [
                               {"input": [2], "expected": True},
                               {"input": [9], "expected": False},
                               {"input": [17], "expected": True},
                           ], ["数论"]),
        make_code_question("code4", "medium", "方差", "variance", ["nums"],
                           "请实现函数 variance(nums)，返回总体方差。保证 nums 非空。",
                           "def variance(nums):\n    pass",
                           "def variance(nums):\n    mean = sum(nums) / len(nums)\n    return sum((x - mean) ** 2 for x in nums) / len(nums)",
                           [
                               {"input": [[1, 2, 3]], "expected": 2 / 3},
                               {"input": [[5, 5]], "expected": 0.0},
                               {"input": [[0, 2]], "expected": 1.0},
                           ], ["统计"]),
        make_code_question("code5", "medium", "矩阵每行求和", "row_sums", ["matrix"],
                           "请实现函数 row_sums(matrix)，返回矩阵每一行元素和组成的列表。",
                           "def row_sums(matrix):\n    pass",
                           "def row_sums(matrix):\n    return [sum(row) for row in matrix]",
                           [
                               {"input": [[[1, 2], [3, 4]]], "expected": [3, 7]},
                               {"input": [[[5], [6], [7]]], "expected": [5, 6, 7]},
                               {"input": [[[]]], "expected": [0]},
                           ], ["矩阵"]),
        make_code_question("code6", "medium", "集合交集大小", "intersection_size", ["a", "b"],
                           "请实现函数 intersection_size(a, b)，返回两个列表交集元素的个数（按去重后集合计算）。",
                           "def intersection_size(a, b):\n    pass",
                           "def intersection_size(a, b):\n    return len(set(a) & set(b))",
                           [
                               {"input": [[1, 2, 3], [2, 3, 4]], "expected": 2},
                               {"input": [[1, 1], [1]], "expected": 1},
                               {"input": [[5], [6]], "expected": 0},
                           ], ["集合"]),
        make_code_question("code7", "project", "统计命题真值个数", "count_true", ["values"],
                           "请实现函数 count_true(values)，返回布尔列表中 True 的个数。",
                           "def count_true(values):\n    pass",
                           "def count_true(values):\n    return sum(1 for v in values if v)",
                           [
                               {"input": [[True, False, True]], "expected": 2},
                               {"input": [[False, False]], "expected": 0},
                               {"input": [[True]], "expected": 1},
                           ], ["逻辑", "统计"]),
    ]
    return concept, code


def build_english_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "c1", "category": "concept", "type": "single",
            "question": "下面哪一项最适合用来描述一个已经完成、且与现在有关的动作？",
            "options": ["一般现在时", "现在完成时", "一般将来时", "过去将来时"],
            "answer": 1,
            "explanation": "现在完成时常表示过去发生、对现在有影响。",
            "tags": ["英语", "时态"],
        },
        {
            "id": "c2", "category": "concept", "type": "multi",
            "question": "下面哪些通常属于提升英语词汇记忆效果的策略？",
            "options": ["结合语境记忆", "按词根词缀归类", "只机械抄写不理解", "间隔复习"],
            "answer": [0, 1, 3],
            "explanation": "语境、词根词缀、间隔复习都更有助于长期记忆。",
            "tags": ["词汇"],
        },
        {
            "id": "c3", "category": "concept", "type": "judge",
            "question": "英语中的主谓一致要求主语和谓语在人称与数上保持协调。",
            "answer": True,
            "explanation": "主谓一致是英语语法基础规则之一。",
            "tags": ["语法"],
        },
        {
            "id": "c4", "category": "concept", "type": "single",
            "question": "如果一句话强调“正在进行的动作”，通常优先考虑哪个时态？",
            "options": ["现在进行时", "一般过去时", "一般现在时", "现在完成时"],
            "answer": 0,
            "explanation": "现在进行时强调当前正在发生。",
            "tags": ["时态"],
        },
        {
            "id": "c5", "category": "concept", "type": "multi",
            "question": "下面哪些属于常见的英语从句类型？",
            "options": ["定语从句", "名词性从句", "状语从句", "矩阵从句"],
            "answer": [0, 1, 2],
            "explanation": "前三者都是常见英语从句类型。",
            "tags": ["从句"],
        },
        {
            "id": "c6", "category": "concept", "type": "judge",
            "question": "只背单词表而完全不接触例句，通常不利于真正掌握词语用法。",
            "answer": True,
            "explanation": "词汇最好结合真实语境理解搭配和用法。",
            "tags": ["词汇"],
        },
        {
            "id": "c7", "category": "concept", "type": "single",
            "question": "在阅读长句时，先定位主干成分通常有什么作用？",
            "options": ["让句子自动变短", "帮助理解句子核心结构", "替代所有词汇学习", "避免分析从句"],
            "answer": 1,
            "explanation": "先找主干可以帮助把握句子的核心语义。",
            "tags": ["阅读", "长难句"],
        },
    ]

    code = [
        make_code_question("code1", "easy", "统计单词数", "count_words", ["text"],
                           "请实现函数 count_words(text)，按空白分词后返回单词数量。",
                           "def count_words(text):\n    pass",
                           "def count_words(text):\n    return len(text.split()) if text.split() else 0",
                           [
                               {"input": ["hello world"], "expected": 2},
                               {"input": ["one"], "expected": 1},
                               {"input": [""], "expected": 0},
                           ], ["字符串", "词汇"]),
        make_code_question("code2", "easy", "小写归一化", "normalize_lower", ["word"],
                           "请实现函数 normalize_lower(word)，返回转成小写后的字符串。",
                           "def normalize_lower(word):\n    pass",
                           "def normalize_lower(word):\n    return word.lower()",
                           [
                               {"input": ["Apple"], "expected": "apple"},
                               {"input": ["USA"], "expected": "usa"},
                               {"input": ["mixEd"], "expected": "mixed"},
                           ], ["字符串"]),
        make_code_question("code3", "medium", "去除标点", "remove_punctuation", ["text"],
                           "请实现函数 remove_punctuation(text)，删除字符串中的逗号、句号、感叹号和问号。",
                           "def remove_punctuation(text):\n    pass",
                           "def remove_punctuation(text):\n    for ch in ',.!?':\n        text = text.replace(ch, '')\n    return text",
                           [
                               {"input": ["Hi, Tom!"], "expected": "Hi Tom"},
                               {"input": ["What?"], "expected": "What"},
                               {"input": ["No.change"], "expected": "Nochange"},
                           ], ["字符串"]),
        make_code_question("code4", "medium", "统计元音字母", "count_vowels", ["text"],
                           "请实现函数 count_vowels(text)，返回字符串中元音字母 aeiou 的个数，不区分大小写。",
                           "def count_vowels(text):\n    pass",
                           "def count_vowels(text):\n    return sum(1 for ch in text.lower() if ch in 'aeiou')",
                           [
                               {"input": ["apple"], "expected": 2},
                               {"input": ["Sky"], "expected": 0},
                               {"input": ["Education"], "expected": 5},
                           ], ["词汇", "字符串"]),
        make_code_question("code5", "medium", "首字母大写", "capitalize_words", ["text"],
                           "请实现函数 capitalize_words(text)，将每个单词首字母变为大写。",
                           "def capitalize_words(text):\n    pass",
                           "def capitalize_words(text):\n    return ' '.join(word.capitalize() for word in text.split())",
                           [
                               {"input": ["hello world"], "expected": "Hello World"},
                               {"input": ["python code"], "expected": "Python Code"},
                               {"input": ["a"], "expected": "A"},
                           ], ["字符串"]),
        make_code_question("code6", "medium", "统计后缀词", "count_suffix_words", ["words", "suffix"],
                           "请实现函数 count_suffix_words(words, suffix)，返回列表中以 suffix 结尾的单词数量。",
                           "def count_suffix_words(words, suffix):\n    pass",
                           "def count_suffix_words(words, suffix):\n    return sum(1 for word in words if word.endswith(suffix))",
                           [
                               {"input": [["reading", "coding", "play"], "ing"], "expected": 2},
                               {"input": [["cat", "dog"], "g"], "expected": 1},
                               {"input": [["one"], "ed"], "expected": 0},
                           ], ["词汇"]),
        make_code_question("code7", "project", "去重保序词表", "dedupe_words", ["words"],
                           "请实现函数 dedupe_words(words)，返回去重后仍保持原始出现顺序的新列表。",
                           "def dedupe_words(words):\n    pass",
                           "def dedupe_words(words):\n    seen = set()\n    result = []\n    for word in words:\n        if word not in seen:\n            seen.add(word)\n            result.append(word)\n    return result",
                           [
                               {"input": [["the", "cat", "the"]], "expected": ["the", "cat"]},
                               {"input": [["a", "a", "a"]], "expected": ["a"]},
                               {"input": [["go", "home"]], "expected": ["go", "home"]},
                           ], ["词汇", "去重"]),
    ]
    return concept, code


def build_linux_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "c1", "category": "concept", "type": "single",
            "question": "查看当前工作目录的最常用命令通常是哪一个？",
            "options": ["pwd", "ps", "chmod", "tar"],
            "answer": 0,
            "explanation": "pwd 用于输出当前工作目录。",
            "tags": ["linux", "命令行"],
        },
        {
            "id": "c2", "category": "concept", "type": "multi",
            "question": "下面哪些命令常用于查看文件内容？",
            "options": ["cat", "less", "head", "mkdir"],
            "answer": [0, 1, 2],
            "explanation": "cat、less、head 都常用于查看文件内容，mkdir 用于建目录。",
            "tags": ["linux", "文件"],
        },
        {
            "id": "c3", "category": "concept", "type": "judge",
            "question": "chmod 用来修改文件或目录权限。",
            "answer": True,
            "explanation": "chmod 是 Linux 中修改权限的常用命令。",
            "tags": ["linux", "权限"],
        },
        {
            "id": "c4", "category": "concept", "type": "single",
            "question": "如果想按名称搜索进程，下面哪个命令最直接？",
            "options": ["pgrep", "touch", "mv", "uname"],
            "answer": 0,
            "explanation": "pgrep 常用于按名称匹配进程。",
            "tags": ["linux", "进程"],
        },
        {
            "id": "c5", "category": "concept", "type": "multi",
            "question": "下面哪些属于常见 Linux 排障信息来源？",
            "options": ["日志文件", "systemctl status", "ss/netstat", "幻灯片动画"],
            "answer": [0, 1, 2],
            "explanation": "日志、服务状态和网络监听信息都很常见。",
            "tags": ["linux", "排障"],
        },
        {
            "id": "c6", "category": "concept", "type": "judge",
            "question": "环境变量 PATH 会影响 shell 查找可执行文件的路径。",
            "answer": True,
            "explanation": "PATH 决定了命令查找顺序。",
            "tags": ["linux", "环境变量"],
        },
        {
            "id": "c7", "category": "concept", "type": "single",
            "question": "查看某个端口是否被监听，下面哪个方向最合理？",
            "options": ["ss -ltnp", "rm -rf", "whoami", "date"],
            "answer": 0,
            "explanation": "ss -ltnp 常用于查看 TCP 监听端口和进程。",
            "tags": ["linux", "网络"],
        },
    ]

    code = [
        make_code_question("code1", "easy", "拼接路径", "join_home_path", ["name"],
                           "请实现函数 join_home_path(name)，返回 '/home/' 与 name 拼接后的路径字符串。",
                           "def join_home_path(name):\n    pass",
                           "def join_home_path(name):\n    return f'/home/{name}'",
                           [
                               {"input": ["alice"], "expected": "/home/alice"},
                               {"input": ["bob"], "expected": "/home/bob"},
                               {"input": ["tmp"], "expected": "/home/tmp"},
                           ], ["linux", "路径"]),
        make_code_question("code2", "easy", "提取文件扩展名", "file_extension", ["filename"],
                           "请实现函数 file_extension(filename)，返回最后一个点号后的扩展名；若没有点号则返回空字符串。",
                           "def file_extension(filename):\n    pass",
                           "def file_extension(filename):\n    return filename.rsplit('.', 1)[1] if '.' in filename else ''",
                           [
                               {"input": ["notes.txt"], "expected": "txt"},
                               {"input": ["archive.tar.gz"], "expected": "gz"},
                               {"input": ["README"], "expected": ""},
                           ], ["linux", "文件"]),
        make_code_question("code3", "medium", "统计隐藏文件", "count_hidden_files", ["names"],
                           "请实现函数 count_hidden_files(names)，返回以 '.' 开头的文件名数量。",
                           "def count_hidden_files(names):\n    pass",
                           "def count_hidden_files(names):\n    return sum(1 for name in names if name.startswith('.'))",
                           [
                               {"input": [[".bashrc", "notes.txt", ".gitignore"]], "expected": 2},
                               {"input": [["file1", "file2"]], "expected": 0},
                               {"input": [[".env"]], "expected": 1},
                           ], ["linux", "文件"]),
        make_code_question("code4", "medium", "筛选可执行权限", "filter_executable", ["permissions"],
                           "请实现函数 filter_executable(permissions)，输入权限字符串列表，返回其中 owner 位可执行（第 3 位为 x）的项数。",
                           "def filter_executable(permissions):\n    pass",
                           "def filter_executable(permissions):\n    return sum(1 for item in permissions if len(item) >= 3 and item[2] == 'x')",
                           [
                               {"input": [["rwxr-xr-x", "rw-r--r--", "r-x------"]], "expected": 2},
                               {"input": [["rw-------"]], "expected": 0},
                               {"input": [["--x------"]], "expected": 1},
                           ], ["linux", "权限"]),
        make_code_question("code5", "medium", "提取日志级别", "extract_log_levels", ["lines"],
                           "请实现函数 extract_log_levels(lines)，从形如 'INFO service started' 的日志行中提取每行第一个单词，返回列表。",
                           "def extract_log_levels(lines):\n    pass",
                           "def extract_log_levels(lines):\n    return [line.split()[0] for line in lines if line.split()]",
                           [
                               {"input": [["INFO started", "ERROR failed"]], "expected": ["INFO", "ERROR"]},
                               {"input": [["WARN low disk"]], "expected": ["WARN"]},
                               {"input": [[""]], "expected": []},
                           ], ["linux", "日志"]),
        make_code_question("code6", "medium", "统计监听端口", "count_listening_ports", ["ports"],
                           "请实现函数 count_listening_ports(ports)，输入端口状态布尔列表，返回 True 的数量。",
                           "def count_listening_ports(ports):\n    pass",
                           "def count_listening_ports(ports):\n    return sum(1 for port in ports if port)",
                           [
                               {"input": [[True, False, True]], "expected": 2},
                               {"input": [[False, False]], "expected": 0},
                               {"input": [[True]], "expected": 1},
                           ], ["linux", "网络"]),
        make_code_question("code7", "project", "统计命令使用频率", "command_frequency", ["commands"],
                           "请实现函数 command_frequency(commands)，返回一个字典，统计每个命令字符串出现的次数。",
                           "def command_frequency(commands):\n    pass",
                           "def command_frequency(commands):\n    result = {}\n    for command in commands:\n        result[command] = result.get(command, 0) + 1\n    return result",
                           [
                               {"input": [["ls", "cd", "ls"]], "expected": {"ls": 2, "cd": 1}},
                               {"input": [["pwd"]], "expected": {"pwd": 1}},
                               {"input": [[]], "expected": {}},
                           ], ["linux", "命令行", "统计"]),
    ]
    return concept, code


def build_llm_app_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "c1", "category": "concept", "type": "single",
            "question": "如果你希望模型稳定输出固定 JSON 字段，最直接的做法通常是什么？",
            "options": ["明确给出 schema 或字段示例", "只说“回答详细一点”", "缩短用户问题", "把 temperature 改成 0.9"],
            "answer": 0,
            "explanation": "结构化输出首先依赖明确的格式约束，而不是只靠模糊提示。",
            "tags": ["llm-app", "structured-output"],
        },
        {
            "id": "c2", "category": "concept", "type": "single",
            "question": "一个最典型的 RAG 基础链路通常是哪个顺序？",
            "options": ["用户问题 -> 检索相关资料 -> 把资料连同问题交给模型生成", "用户问题 -> 直接让模型猜 -> 最后再检索", "先微调整个模型 -> 再决定要不要回答", "先删除上下文 -> 再调用工具"],
            "answer": 0,
            "explanation": "RAG 的核心是 retrieval + generation，先检索再生成。",
            "tags": ["llm-app", "rag"],
        },
        {
            "id": "c3", "category": "concept", "type": "judge",
            "question": "提示词写得再长，也不能稳定替代外部检索到的真实知识。",
            "answer": True,
            "explanation": "Prompt 可以改善表达和约束，但不能凭空补足系统没有提供的事实来源。",
            "tags": ["llm-app", "prompting", "rag"],
        },
        {
            "id": "c4", "category": "concept", "type": "single",
            "question": "LangChain 在 LLM 应用里更常见的定位是什么？",
            "options": ["用于组织 prompts、models、retrievers、tools 等组件工作流", "替代操作系统内核", "直接存储 GPU 显存", "把 Python 自动编译成 C"],
            "answer": 0,
            "explanation": "LangChain 更像应用编排层，帮助把常见组件串起来。",
            "tags": ["llm-app", "langchain", "workflow"],
        },
        {
            "id": "c5", "category": "concept", "type": "multi",
            "question": "设计 tool calling 时，哪些做法通常更合理？",
            "options": ["工具输入输出结构尽量清晰", "把每个工具职责定义得尽量单一", "让模型自己猜工具参数字段", "为工具返回结果保留可解析结构"],
            "answer": [0, 1, 3],
            "explanation": "工具设计应强调清晰 schema、单一职责和可解析返回，而不是依赖模型盲猜。",
            "tags": ["llm-app", "tools"],
        },
        {
            "id": "c6", "category": "concept", "type": "judge",
            "question": "Agent workflow 通常意味着模型会在多步过程中决定下一步动作，并可能调用不同工具。",
            "answer": True,
            "explanation": "这是 agent 的常见特征：按状态推进、做决策、可能调用工具。",
            "tags": ["llm-app", "agent"],
        },
        {
            "id": "c7", "category": "concept", "type": "single",
            "question": "下面哪一项最不属于 LLM 应用 eval 的常见指标？",
            "options": ["回答正确性", "检索相关性", "延迟与成本", "显示器刷新率"],
            "answer": 3,
            "explanation": "Eval 常关注质量、相关性、延迟、成本等，显示器刷新率与应用评测无关。",
            "tags": ["llm-app", "eval"],
        },
    ]

    code = [
        make_code_question("code1", "easy", "构造 messages 列表", "build_messages", ["system_prompt", "user_question"],
                           "请实现函数 build_messages(system_prompt, user_question)，返回 Claude/OpenAI 风格的 messages 列表，格式为 [{'role': 'system', 'content': ...}, {'role': 'user', 'content': ...}]。",
                           "def build_messages(system_prompt, user_question):\n    pass",
                           "def build_messages(system_prompt, user_question):\n    return [\n        {'role': 'system', 'content': system_prompt},\n        {'role': 'user', 'content': user_question},\n    ]",
                           [
                               {"input": ["你是助手", "总结这段文本"], "expected": [{"role": "system", "content": "你是助手"}, {"role": "user", "content": "总结这段文本"}]},
                               {"input": ["只返回 JSON", "给我结果"], "expected": [{"role": "system", "content": "只返回 JSON"}, {"role": "user", "content": "给我结果"}]},
                               {"input": ["", "hello"], "expected": [{"role": "system", "content": ""}, {"role": "user", "content": "hello"}]},
                           ], ["llm-app", "messages", "prompting"]),
        make_code_question("code2", "easy", "提取结构化字段", "extract_answer_field", ["payload", "field"],
                           "请实现函数 extract_answer_field(payload, field)，当 payload 是字典且包含 field 时返回对应值，否则返回 None。",
                           "def extract_answer_field(payload, field):\n    pass",
                           "def extract_answer_field(payload, field):\n    if not isinstance(payload, dict):\n        return None\n    return payload.get(field)",
                           [
                               {"input": [{"answer": "42", "confidence": 0.8}, "answer"], "expected": "42"},
                               {"input": [{"answer": "ok"}, "confidence"], "expected": None},
                               {"input": [None, "answer"], "expected": None},
                           ], ["llm-app", "structured-output"]),
        make_code_question("code3", "medium", "筛选检索结果", "select_retrieved_docs", ["docs", "min_score"],
                           "请实现函数 select_retrieved_docs(docs, min_score)，输入形如 {'text': ..., 'score': ...} 的字典列表，返回 score 大于等于 min_score 的文档列表。",
                           "def select_retrieved_docs(docs, min_score):\n    pass",
                           "def select_retrieved_docs(docs, min_score):\n    return [doc for doc in docs if doc.get('score', 0) >= min_score]",
                           [
                               {"input": [[{"text": "A", "score": 0.91}, {"text": "B", "score": 0.4}], 0.8], "expected": [{"text": "A", "score": 0.91}]},
                               {"input": [[{"text": "A", "score": 0.5}, {"text": "B", "score": 0.7}], 0.7], "expected": [{"text": "B", "score": 0.7}]},
                               {"input": [[], 0.6], "expected": []},
                           ], ["llm-app", "rag", "retrieval"]),
        make_code_question("code4", "medium", "格式化 RAG 上下文", "format_rag_context", ["chunks"],
                           "请实现函数 format_rag_context(chunks)，把若干文本片段按 '【片段1】...\n\n【片段2】...' 的形式拼接；空列表返回空字符串。",
                           "def format_rag_context(chunks):\n    pass",
                           "def format_rag_context(chunks):\n    parts = []\n    for index, chunk in enumerate(chunks, start=1):\n        parts.append(f'【片段{index}】{chunk}')\n    return '\\n\\n'.join(parts)",
                           [
                               {"input": [["文档A", "文档B"]], "expected": "【片段1】文档A\n\n【片段2】文档B"},
                               {"input": [["Only one"]], "expected": "【片段1】Only one"},
                               {"input": [[]], "expected": ""},
                           ], ["llm-app", "rag", "context"]),
        make_code_question("code5", "medium", "收集工具调用名", "collect_tool_call_names", ["tool_calls"],
                           "请实现函数 collect_tool_call_names(tool_calls)，输入形如 {'name': ...} 的工具调用列表，返回其中所有 name 值组成的列表，缺少 name 的项跳过。",
                           "def collect_tool_call_names(tool_calls):\n    pass",
                           "def collect_tool_call_names(tool_calls):\n    return [call['name'] for call in tool_calls if 'name' in call]",
                           [
                               {"input": [[{"name": "search"}, {"name": "calculator"}]], "expected": ["search", "calculator"]},
                               {"input": [[{"name": "browser"}, {}]], "expected": ["browser"]},
                               {"input": [[]], "expected": []},
                           ], ["llm-app", "tools", "agent"]),
        make_code_question("code6", "medium", "计算回答准确率", "compute_accuracy", ["results"],
                           "请实现函数 compute_accuracy(results)，输入布尔列表，返回 True 所占比例；空列表返回 0。",
                           "def compute_accuracy(results):\n    pass",
                           "def compute_accuracy(results):\n    return sum(1 for item in results if item) / len(results) if results else 0",
                           [
                               {"input": [[True, True, False]], "expected": 2 / 3},
                               {"input": [[False, False]], "expected": 0.0},
                               {"input": [[]], "expected": 0},
                           ], ["llm-app", "eval"]),
        make_code_question("code7", "project", "统计文档来源分布", "count_docs_by_source", ["docs"],
                           "请实现函数 count_docs_by_source(docs)，输入含 source 字段的字典列表，返回 source 到数量的映射；缺少 source 时归到 'unknown'。",
                           "def count_docs_by_source(docs):\n    pass",
                           "def count_docs_by_source(docs):\n    result = {}\n    for doc in docs:\n        source = doc.get('source', 'unknown')\n        result[source] = result.get(source, 0) + 1\n    return result",
                           [
                               {"input": [[{"source": "faq"}, {"source": "faq"}, {"source": "wiki"}]], "expected": {"faq": 2, "wiki": 1}},
                               {"input": [[{"title": "x"}]], "expected": {"unknown": 1}},
                               {"input": [[]], "expected": {}},
                           ], ["llm-app", "rag", "project"]),
    ]
    return concept, code


def build_general_cs_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "c1", "category": "concept", "type": "single",
            "question": "HTTP 404 通常表示什么？",
            "options": ["资源未找到", "鉴权成功", "服务启动完成", "数据库已备份"],
            "answer": 0,
            "explanation": "404 表示请求的资源不存在或未找到。",
            "tags": ["general-cs", "http"],
        },
        {
            "id": "c2", "category": "concept", "type": "multi",
            "question": "下面哪些属于常见工程调试手段？",
            "options": ["日志", "断点", "最小复现", "随意删除代码"],
            "answer": [0, 1, 2],
            "explanation": "前三者都属于常见且合理的调试手段。",
            "tags": ["general-cs", "debug"],
        },
        {
            "id": "c3", "category": "concept", "type": "judge",
            "question": "JSON 是一种常见的数据交换格式。",
            "answer": True,
            "explanation": "JSON 在接口与配置中很常见。",
            "tags": ["general-cs", "json"],
        },
        {
            "id": "c4", "category": "concept", "type": "single",
            "question": "git commit 的主要作用是什么？",
            "options": ["保存一份版本快照到本地历史", "直接上线到生产", "删除仓库", "自动修复 bug"],
            "answer": 0,
            "explanation": "commit 用于记录当前版本历史。",
            "tags": ["general-cs", "git"],
        },
        {
            "id": "c5", "category": "concept", "type": "multi",
            "question": "一个典型 Web 应用常见包含哪些部分？",
            "options": ["前端", "后端接口", "数据库", "机械键盘灯效"],
            "answer": [0, 1, 2],
            "explanation": "前三项都很常见。",
            "tags": ["general-cs", "architecture"],
        },
        {
            "id": "c6", "category": "concept", "type": "judge",
            "question": "自动化测试的一个重要价值是帮助更早发现回归问题。",
            "answer": True,
            "explanation": "测试可以降低回归风险。",
            "tags": ["general-cs", "testing"],
        },
        {
            "id": "c7", "category": "concept", "type": "single",
            "question": "部署后发现接口异常，通常第一步更合理的是？",
            "options": ["查看日志和错误信息", "直接删库", "马上重装系统", "忽略报警"],
            "answer": 0,
            "explanation": "先看日志和报错信息最基本。",
            "tags": ["general-cs", "ops"],
        },
    ]

    code = [
        make_code_question("code1", "easy", "统计状态码", "count_status", ["codes", "target"],
                           "请实现函数 count_status(codes, target)，返回列表中等于 target 的状态码数量。",
                           "def count_status(codes, target):\n    pass",
                           "def count_status(codes, target):\n    return sum(1 for code in codes if code == target)",
                           [
                               {"input": [[200, 404, 200], 200], "expected": 2},
                               {"input": [[500, 500], 404], "expected": 0},
                               {"input": [[201], 201], "expected": 1},
                           ], ["general-cs", "http"]),
        make_code_question("code2", "easy", "提取 JSON 键", "json_keys", ["obj"],
                           "请实现函数 json_keys(obj)，返回字典所有键组成的列表。",
                           "def json_keys(obj):\n    pass",
                           "def json_keys(obj):\n    return list(obj.keys())",
                           [
                               {"input": [{"a": 1, "b": 2}], "expected": ["a", "b"]},
                               {"input": [{"name": "x"}], "expected": ["name"]},
                               {"input": [{}], "expected": []},
                           ], ["general-cs", "json"]),
        make_code_question("code3", "medium", "筛选错误日志", "filter_error_logs", ["logs"],
                           "请实现函数 filter_error_logs(logs)，返回包含 'ERROR' 子串的日志行列表。",
                           "def filter_error_logs(logs):\n    pass",
                           "def filter_error_logs(logs):\n    return [log for log in logs if 'ERROR' in log]",
                           [
                               {"input": [["INFO ok", "ERROR failed"]], "expected": ["ERROR failed"]},
                               {"input": [["WARN a", "WARN b"]], "expected": []},
                               {"input": [["ERROR x", "ERROR y"]], "expected": ["ERROR x", "ERROR y"]},
                           ], ["general-cs", "logs"]),
        make_code_question("code4", "medium", "统计分支名", "branch_frequency", ["branches"],
                           "请实现函数 branch_frequency(branches)，返回每个分支名出现次数的字典。",
                           "def branch_frequency(branches):\n    pass",
                           "def branch_frequency(branches):\n    result = {}\n    for branch in branches:\n        result[branch] = result.get(branch, 0) + 1\n    return result",
                           [
                               {"input": [["main", "dev", "main"]], "expected": {"main": 2, "dev": 1}},
                               {"input": [["feature"]], "expected": {"feature": 1}},
                               {"input": [[]], "expected": {}},
                           ], ["general-cs", "git"]),
        make_code_question("code5", "medium", "查找慢请求", "count_slow_requests", ["durations", "threshold"],
                           "请实现函数 count_slow_requests(durations, threshold)，返回耗时大于阈值的请求数。",
                           "def count_slow_requests(durations, threshold):\n    pass",
                           "def count_slow_requests(durations, threshold):\n    return sum(1 for duration in durations if duration > threshold)",
                           [
                               {"input": [[120, 80, 300], 100], "expected": 2},
                               {"input": [[10, 20], 50], "expected": 0},
                               {"input": [[51], 50], "expected": 1},
                           ], ["general-cs", "performance"]),
        make_code_question("code6", "medium", "统计通过测试", "passed_tests", ["results"],
                           "请实现函数 passed_tests(results)，输入布尔列表，返回通过数量。",
                           "def passed_tests(results):\n    pass",
                           "def passed_tests(results):\n    return sum(1 for result in results if result)",
                           [
                               {"input": [[True, False, True]], "expected": 2},
                               {"input": [[False]], "expected": 0},
                               {"input": [[]], "expected": 0},
                           ], ["general-cs", "testing"]),
        make_code_question("code7", "project", "按环境统计配置项", "count_env_keys", ["configs"],
                           "请实现函数 count_env_keys(configs)，输入环境到配置字典的映射，返回环境到键数量的映射。",
                           "def count_env_keys(configs):\n    pass",
                           "def count_env_keys(configs):\n    return {env: len(values) for env, values in configs.items()}",
                           [
                               {"input": [{"dev": {"DEBUG": True, "PORT": 8000}, "prod": {"PORT": 80}}], "expected": {"dev": 2, "prod": 1}},
                               {"input": [{"test": {}}], "expected": {"test": 0}},
                               {"input": [{}], "expected": {}},
                           ], ["general-cs", "config"]),
    ]
    return concept, code


def make_python_metadata(
    stage: str,
    cluster: str,
    subskills: list[str],
    question_role: str,
    prerequisites: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "family": "python",
        "stage": stage,
        "cluster": cluster,
        "subskills": subskills,
        "question_role": question_role,
        "prerequisites": prerequisites or [],
    }


def make_python_concept_question(
    qid: str,
    qtype: str,
    difficulty: str,
    question: str,
    explanation: str,
    tags: list[str],
    *,
    answer: Any,
    options: list[str] | None = None,
    stage: str,
    cluster: str,
    subskills: list[str],
    question_role: str,
    prerequisites: list[str] | None = None,
) -> dict[str, Any]:
    item = {
        "id": qid,
        "category": "concept",
        "type": qtype,
        "difficulty": difficulty,
        "question": question,
        "answer": answer,
        "explanation": explanation,
        "tags": tags,
    }
    if options is not None:
        item["options"] = options
    item.update(make_python_metadata(stage, cluster, subskills, question_role, prerequisites))
    return item


def make_written_question(
    qid: str,
    difficulty: str,
    question: str,
    prompt: str,
    tags: list[str],
    *,
    reference_points: list[str] | None = None,
    grading_hint: str | None = None,
    stage: str | None = None,
    cluster: str | None = None,
    subskills: list[str] | None = None,
    question_role: str | None = None,
    prerequisites: list[str] | None = None,
) -> dict[str, Any]:
    item = {
        "id": qid,
        "category": "open",
        "type": "written",
        "difficulty": difficulty,
        "question": question,
        "prompt": prompt,
        "description": prompt,
        "tags": tags,
    }
    normalized_reference_points = normalize_string_list(reference_points or [])
    if normalized_reference_points:
        item["reference_points"] = normalized_reference_points
    if str(grading_hint or "").strip():
        item["grading_hint"] = str(grading_hint).strip()
    if stage and cluster and subskills is not None and question_role:
        item.update(make_python_metadata(stage, cluster, subskills, question_role, prerequisites))
    elif question_role:
        item["question_role"] = question_role
    return item


def make_code_question(
    qid: str,
    difficulty: str,
    title: str,
    function_name: str,
    params: list[str],
    prompt: str,
    starter_code: str,
    solution_code: str,
    test_cases: list[dict[str, Any]],
    tags: list[str],
    *,
    stage: str | None = None,
    cluster: str | None = None,
    subskills: list[str] | None = None,
    question_role: str | None = None,
    prerequisites: list[str] | None = None,
) -> dict[str, Any]:
    item = {
        "id": qid,
        "category": "code",
        "type": "function",
        "difficulty": difficulty,
        "title": title,
        "prompt": prompt,
        "description": prompt,
        "function_name": function_name,
        "params": params,
        "starter_code": starter_code,
        "solution_code": solution_code,
        "test_cases": test_cases,
        "tags": tags,
        "editor_language": "python",
        "language_label": "Python",
    }
    if stage and cluster and subskills is not None and question_role:
        item.update(make_python_metadata(stage, cluster, subskills, question_role, prerequisites))
    return item


def build_python_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        make_python_concept_question(
            "py-c1", "single", "easy",
            "在 Python 中，如果一个函数没有显式写 return，调用结果默认是什么？",
            "Python 函数未显式 return 时会默认返回 None。",
            ["python", "函数", "返回值", "stage1"],
            answer=2,
            options=["0", "False", "None", "空字符串"],
            stage="stage1",
            cluster="functions-foundations",
            subskills=["函数返回值", "None", "基础函数语义"],
            question_role="review",
        ),
        make_python_concept_question(
            "py-c2", "multi", "medium",
            "关于 Python 函数参数，下面哪些说法是正确的？",
            "可变默认参数会复用同一个对象；关键字参数常能提升可读性。位置参数应先于关键字参数；关键字调用依赖参数名。",
            ["python", "函数", "参数", "默认参数", "stage1"],
            answer=[0, 1],
            options=["可变默认参数可能带来跨调用共享状态", "关键字参数可以提升调用可读性", "位置参数必须写在关键字参数后面", "形参名只影响函数定义，不影响关键字调用"],
            stage="stage1",
            cluster="functions-foundations",
            subskills=["函数参数", "默认参数", "关键字参数"],
            question_role="learn",
        ),
        make_python_concept_question(
            "py-c3", "judge", "easy",
            "使用 with open(...) as f: 可以在代码块结束后自动关闭文件。",
            "with 会配合上下文管理协议在离开代码块时释放资源。",
            ["python", "文件读写", "with", "上下文管理器", "stage1", "stage3"],
            answer=True,
            stage="stage1",
            cluster="files-and-io",
            subskills=["文件读写", "with", "资源释放"],
            question_role="learn",
        ),
        make_python_concept_question(
            "py-c4", "single", "medium",
            "处理 Python 报错时，先看 traceback 的核心价值通常是什么？",
            "traceback 最直接的作用是告诉你错误类型、调用链和具体行号。",
            ["python", "异常处理", "调试", "traceback", "stage1"],
            answer=1,
            options=["自动修复代码", "定位异常类型与触发位置", "替代单元测试", "判断代码风格是否 Pythonic"],
            stage="stage1",
            cluster="exceptions-and-debugging",
            subskills=["traceback", "异常定位", "调试"],
            question_role="review",
        ),
        make_python_concept_question(
            "py-c5", "multi", "medium",
            "关于 try-except 的使用，下面哪些做法更合理？",
            "异常处理应尽量精确，关注边界操作，并保留足够上下文；无条件吞异常会降低可调试性。",
            ["python", "异常处理", "调试", "stage1"],
            answer=[0, 2, 3],
            options=["只捕获你预期会发生的异常类型", "在 except 里吞掉所有异常且不处理", "把可能失败的边界操作包进 try", "必要时记录上下文信息帮助排查"],
            stage="stage1",
            cluster="exceptions-and-debugging",
            subskills=["try-except", "异常边界", "错误上下文"],
            question_role="learn",
        ),
        make_python_concept_question(
            "py-c11", "single", "easy",
            "在《Python编程：从入门到实践》第 10 章的写法里，读取一个文本文件内容更贴近哪种调用？",
            "本章使用 pathlib.Path，常见写法是先构造 Path 对象，再调用 read_text() 读取文本内容。",
            ["python", "pathlib", "Path", "read_text", "文件读写", "stage1"],
            answer=0,
            options=["Path('data.txt').read_text()", "json.dumps('data.txt')", "list.read_text('data.txt')", "try.read_text('data.txt')"],
            stage="stage1",
            cluster="files-pathlib-json-exceptions",
            subskills=["pathlib.Path", "read_text", "文本读取"],
            question_role="learn",
        ),
        make_python_concept_question(
            "py-c12", "multi", "medium",
            "关于 Path.write_text()，下面哪些说法更准确？",
            "Path.write_text() 用于把字符串写入目标路径；它是 pathlib.Path 对象的方法，适合和 read_text() 成对理解。",
            ["python", "pathlib", "Path", "write_text", "文件读写", "stage1"],
            answer=[0, 1, 3],
            options=["它通常写在 Path 对象上", "它用于写入字符串内容", "它返回 json.loads 的结果", "它和 read_text() 都是 pathlib 场景中的常见文本 API"],
            stage="stage1",
            cluster="files-pathlib-json-exceptions",
            subskills=["pathlib.Path", "write_text", "文本写入"],
            question_role="learn",
        ),
        make_python_concept_question(
            "py-c13", "single", "medium",
            "json.dumps() 和 json.loads() 的方向分别是什么？",
            "dumps 是把 Python 对象序列化为 JSON 字符串；loads 是把 JSON 字符串解析回 Python 对象。",
            ["python", "json.dumps", "json.loads", "JSON", "stage1"],
            answer=1,
            options=["dumps 读文件，loads 写文件", "dumps: Python 对象 -> JSON 字符串；loads: JSON 字符串 -> Python 对象", "dumps 捕获异常，loads 打印 traceback", "两者都只能处理 pathlib.Path 对象"],
            stage="stage1",
            cluster="files-pathlib-json-exceptions",
            subskills=["json.dumps", "json.loads", "序列化与反序列化"],
            question_role="learn",
        ),
        make_python_concept_question(
            "py-c14", "multi", "medium",
            "围绕文件读取和 JSON 解析写 try-except 时，哪些边界更值得优先处理？",
            "文件不存在、JSON 字符串格式错误等都属于文件/JSON 边界上常见、可预期的失败点。",
            ["python", "try-except", "FileNotFoundError", "JSON", "pathlib", "stage1"],
            answer=[0, 1, 2],
            options=["目标文件不存在", "JSON 字符串格式不合法", "路径指向的内容不是预期格式", "为了省事捕获所有异常并直接 pass"],
            stage="stage1",
            cluster="files-pathlib-json-exceptions",
            subskills=["try-except", "FileNotFoundError", "JSON 边界"],
            question_role="bridge",
        ),
        make_python_concept_question(
            "py-c15", "judge", "easy",
            "json.loads() 接收 JSON 格式字符串并返回对应的 Python 对象。",
            "loads 的 s 可以理解为 string；它处理的是 JSON 字符串，不是文件路径本身。",
            ["python", "json.loads", "JSON", "stage1"],
            answer=True,
            stage="stage1",
            cluster="files-pathlib-json-exceptions",
            subskills=["json.loads", "JSON 字符串", "Python 类型映射"],
            question_role="test",
        ),
        make_python_concept_question(
            "py-c17", "judge", "easy",
            "json.dumps() 会把 Python 对象转换为可写入文件的 JSON 格式字符串。",
            "第 10 章的 number_writer.py 先用 json.dumps(numbers) 得到字符串，再用 Path.write_text(contents) 写入 numbers.json。",
            ["python", "json.dumps", "JSON", "Path.write_text", "stage1"],
            answer=True,
            stage="stage1",
            cluster="files-pathlib-json-exceptions",
            subskills=["json.dumps", "JSON 字符串", "Path.write_text"],
            question_role="test",
        ),
        make_python_concept_question(
            "py-c16", "judge", "easy",
            "Path.read_text() 的调用对象通常是 pathlib.Path 对象，而不是普通 list。",
            "read_text() 是 Path 对象的文本读取方法；普通列表没有这个文件读取职责。",
            ["python", "pathlib", "Path.read_text", "stage1"],
            answer=True,
            stage="stage1",
            cluster="files-pathlib-json-exceptions",
            subskills=["pathlib.Path", "read_text", "对象方法"],
            question_role="review",
        ),
        make_python_concept_question(
            "py-c6", "single", "medium",
            "在 pandas 中，如果你想按条件筛选行，最常见的写法是哪一种？",
            "按条件筛选最常见的是布尔条件配合 loc 或直接 df[mask]。",
            ["python", "pandas", "筛选", "DataFrame", "stage2"],
            answer=0,
            options=["df.loc[df['score'] > 60]", "df.groupby('score')", "df.merge(df2)", "df.pivot_table(index='score')"],
            stage="stage2",
            cluster="pandas-filtering",
            subskills=["布尔筛选", "DataFrame", "loc"],
            question_role="learn",
            prerequisites=["函数基础", "列表与字典", "基本数据读取"],
        ),
        make_python_concept_question(
            "py-c7", "multi", "hard",
            "关于 groupby、merge、pivot/reshape，下面哪些理解更准确？",
            "groupby、merge、pivot 分别对应聚合、连接、重塑，不等同于简单过滤。",
            ["python", "pandas", "groupby", "merge", "pivot", "reshape", "stage2"],
            answer=[0, 1, 2],
            options=["groupby 常用于分组后聚合统计", "merge 常用于按键连接多张表", "pivot/reshape 主要用于重塑表结构", "它们本质上都只是在做按行过滤"],
            stage="stage2",
            cluster="pandas-groupby-merge-reshape",
            subskills=["groupby", "merge", "pivot", "reshape"],
            question_role="bridge",
            prerequisites=["pandas 基础筛选", "DataFrame 结构理解"],
        ),
        make_python_concept_question(
            "py-c8", "judge", "medium",
            "NumPy / pandas 的很多操作之所以高效，和向量化思维有关。",
            "向量化意味着尽量让底层批量处理数据，而不是在 Python 层面逐元素循环。",
            ["python", "numpy", "pandas", "向量化", "stage2"],
            answer=True,
            stage="stage2",
            cluster="data-cleaning-and-vectorization",
            subskills=["向量化", "NumPy", "pandas 性能思维"],
            question_role="bridge",
            prerequisites=["数组与 DataFrame 基础"],
        ),
        make_python_concept_question(
            "py-c9", "single", "medium",
            "下面哪种写法通常更符合 Pythonic 风格？",
            "简单映射和过滤场景下，列表推导式通常更清晰简洁。",
            ["python", "pythonic", "列表推导式", "stage3"],
            answer=1,
            options=["先创建空列表，再在 10 行循环里 append 简单映射结果", "在表达简单映射时使用列表推导式", "所有逻辑都写进一个超长函数", "为了显得高级到处手写迭代器协议"],
            stage="stage3",
            cluster="pythonic-expressions",
            subskills=["列表推导式", "Pythonic 表达", "代码简洁性"],
            question_role="learn",
            prerequisites=["循环", "条件表达式", "函数基础"],
        ),
        make_python_concept_question(
            "py-c10", "multi", "hard",
            "关于生成器与上下文管理器，下面哪些说法更准确？",
            "生成器适合惰性迭代；上下文管理器用于成对资源管理；with 依赖上下文管理协议。生成器并非所有场景都优于列表。",
            ["python", "pythonic", "生成器", "上下文管理器", "stage3"],
            answer=[0, 1, 3],
            options=["生成器适合按需产出数据，减少一次性占用内存", "上下文管理器常用于资源申请与释放配对", "生成器一定比列表推导式更快且总是更适合", "with 语句背后依赖上下文管理协议"],
            stage="stage3",
            cluster="generators-and-context-managers",
            subskills=["生成器", "上下文管理器", "惰性迭代"],
            question_role="bridge",
            prerequisites=["迭代器基础", "函数基础"],
        ),
    ]

    code = [
        make_code_question("py-code1", "easy", "提取偶数", "extract_even_numbers", ["nums"],
                           "请实现函数 extract_even_numbers(nums)，返回列表中所有偶数组成的新列表，保持原顺序。",
                           "def extract_even_numbers(nums):\n    pass",
                           "def extract_even_numbers(nums):\n    return [num for num in nums if num % 2 == 0]",
                           [
                               {"input": [[1, 2, 3, 4]], "expected": [2, 4]},
                               {"input": [[1, 3, 5]], "expected": []},
                               {"input": [[0, -2, 7]], "expected": [0, -2]},
                           ], ["python", "函数", "列表处理", "stage1"],
                           stage="stage1", cluster="functions-foundations", subskills=["函数定义", "列表遍历", "条件过滤"], question_role="review"),
        make_code_question("py-code2", "easy", "规范化姓名", "normalize_names", ["names"],
                           "请实现函数 normalize_names(names)，去掉每个姓名首尾空白并转成 title case，返回新列表。",
                           "def normalize_names(names):\n    pass",
                           "def normalize_names(names):\n    return [name.strip().title() for name in names]",
                           [
                               {"input": [[" alice ", "BOB"]], "expected": ["Alice", "Bob"]},
                               {"input": [["tom"]], "expected": ["Tom"]},
                               {"input": [["  mary jane  "]], "expected": ["Mary Jane"]},
                           ], ["python", "字符串", "函数", "stage1"],
                           stage="stage1", cluster="functions-foundations", subskills=["字符串方法", "列表构造", "函数返回值"], question_role="learn"),
        make_code_question("py-code3", "easy", "安全除法", "safe_divide", ["a", "b"],
                           "请实现函数 safe_divide(a, b)：若 b 为 0 返回 None，否则返回 a / b。",
                           "def safe_divide(a, b):\n    pass",
                           "def safe_divide(a, b):\n    if b == 0:\n        return None\n    return a / b",
                           [
                               {"input": [6, 3], "expected": 2.0},
                               {"input": [5, 0], "expected": None},
                               {"input": [7, 2], "expected": 3.5},
                           ], ["python", "异常处理", "函数", "stage1"],
                           stage="stage1", cluster="exceptions-and-debugging", subskills=["边界判断", "返回值设计", "安全处理"], question_role="learn"),
        make_code_question("py-code4", "medium", "解析 CSV 行", "parse_csv_row", ["row"],
                           "请实现函数 parse_csv_row(row)，按逗号切分字符串，并去掉每个字段首尾空白。",
                           "def parse_csv_row(row):\n    pass",
                           "def parse_csv_row(row):\n    return [part.strip() for part in row.split(',')]",
                           [
                               {"input": ["alice, 18, Chongqing"], "expected": ["alice", "18", "Chongqing"]},
                               {"input": ["a,b,c"], "expected": ["a", "b", "c"]},
                               {"input": [" one , two "], "expected": ["one", "two"]},
                           ], ["python", "文件读写", "CSV", "stage1"],
                           stage="stage1", cluster="files-and-io", subskills=["split", "strip", "CSV 预处理"], question_role="bridge"),
        make_code_question("py-code10", "easy", "读取文本并去除首尾空白", "clean_text_from_path", ["path_str"],
                           "请实现函数 clean_text_from_path(path_str)，使用 pathlib.Path(path_str).read_text() 读取文本，并返回去掉首尾空白后的字符串。",
                           "from pathlib import Path\n\ndef clean_text_from_path(path_str):\n    pass",
                           "from pathlib import Path\n\ndef clean_text_from_path(path_str):\n    return Path(path_str).read_text().strip()",
                           [
                               {"input": ["note.txt"], "expected": "hello", "files": {"note.txt": "  hello\n"}},
                               {"input": ["empty.txt"], "expected": "", "files": {"empty.txt": "  \n"}},
                           ], ["python", "pathlib", "Path.read_text", "文件读写", "stage1"],
                           stage="stage1", cluster="files-pathlib-json-exceptions", subskills=["pathlib.Path", "read_text", "strip"], question_role="learn"),
        make_code_question("py-code11", "easy", "写入文本", "write_message", ["path_str", "message"],
                           "请实现函数 write_message(path_str, message)，使用 pathlib.Path(path_str).write_text(message) 写入文本，并返回写入的字符数。",
                           "from pathlib import Path\n\ndef write_message(path_str, message):\n    pass",
                           "from pathlib import Path\n\ndef write_message(path_str, message):\n    return Path(path_str).write_text(message)",
                           [
                               {"input": ["out.txt", "hello"], "expected": 5},
                               {"input": ["empty_out.txt", ""], "expected": 0},
                           ], ["python", "pathlib", "Path.write_text", "文件读写", "stage1"],
                           stage="stage1", cluster="files-pathlib-json-exceptions", subskills=["pathlib.Path", "write_text", "返回值"], question_role="learn"),
        make_code_question("py-code12", "medium", "解析 JSON 字符串", "load_user", ["raw"],
                           "请实现函数 load_user(raw)，使用 json.loads(raw) 把 JSON 字符串解析为 Python 对象，并返回 name 字段。",
                           "import json\n\ndef load_user(raw):\n    pass",
                           "import json\n\ndef load_user(raw):\n    data = json.loads(raw)\n    return data.get('name')",
                           [
                               {"input": ['{\"name\": \"Ada\", \"age\": 30}'], "expected": "Ada"},
                               {"input": ['{\"name\": \"Lin\"}'], "expected": "Lin"},
                           ], ["python", "json.loads", "JSON", "stage1"],
                           stage="stage1", cluster="files-pathlib-json-exceptions", subskills=["json.loads", "dict.get", "JSON 反序列化"], question_role="learn"),
        make_code_question("py-code13", "medium", "序列化偏好设置", "dump_settings", ["settings"],
                           "请实现函数 dump_settings(settings)，使用 json.dumps(settings, ensure_ascii=False) 返回 JSON 字符串。",
                           "import json\n\ndef dump_settings(settings):\n    pass",
                           "import json\n\ndef dump_settings(settings):\n    return json.dumps(settings, ensure_ascii=False)",
                           [
                               {"input": [{"theme": "dark"}], "expected": '{"theme": "dark"}'},
                               {"input": [{"name": "重庆"}], "expected": '{"name": "重庆"}'},
                           ], ["python", "json.dumps", "JSON", "stage1"],
                           stage="stage1", cluster="files-pathlib-json-exceptions", subskills=["json.dumps", "ensure_ascii", "JSON 序列化"], question_role="bridge"),
        make_code_question("py-code14", "medium", "安全读取 JSON", "safe_load_json", ["path_str"],
                           "请实现函数 safe_load_json(path_str)，用 Path.read_text() 读取文件，再用 json.loads() 解析；如果文件不存在或 JSON 不合法，返回 None。",
                           "from pathlib import Path\nimport json\n\ndef safe_load_json(path_str):\n    pass",
                           "from pathlib import Path\nimport json\n\ndef safe_load_json(path_str):\n    try:\n        return json.loads(Path(path_str).read_text())\n    except (FileNotFoundError, json.JSONDecodeError):\n        return None",
                           [
                               {"input": ["user.json"], "expected": {"name": "Ada"}, "files": {"user.json": "{\"name\": \"Ada\"}"}},
                               {"input": ["bad.json"], "expected": None, "files": {"bad.json": "not json"}},
                               {"input": ["missing.json"], "expected": None},
                           ], ["python", "pathlib", "Path.read_text", "json.loads", "try-except", "stage1"],
                           stage="stage1", cluster="files-pathlib-json-exceptions", subskills=["Path.read_text", "json.loads", "try-except"], question_role="test"),
        make_code_question("py-code5", "medium", "按城市计数", "count_rows_by_city", ["rows"],
                           "请实现函数 count_rows_by_city(rows)。rows 是字典列表，每项包含 city 字段；返回每个 city 的出现次数。",
                           "def count_rows_by_city(rows):\n    pass",
                           "def count_rows_by_city(rows):\n    result = {}\n    for row in rows:\n        city = row.get('city')\n        result[city] = result.get(city, 0) + 1\n    return result",
                           [
                               {"input": [[{"city": "重庆"}, {"city": "北京"}, {"city": "重庆"}]], "expected": {"重庆": 2, "北京": 1}},
                               {"input": [[{"city": "上海"}]], "expected": {"上海": 1}},
                               {"input": [[]], "expected": {}},
                           ], ["python", "pandas", "groupby", "聚合", "stage2"],
                           stage="stage2", cluster="pandas-groupby-merge-reshape", subskills=["分组统计", "字典累加", "聚合思维"], question_role="learn", prerequisites=["DataFrame 基础", "字典计数"]),
        make_code_question("py-code6", "medium", "合并用户分数", "merge_user_scores", ["users", "scores"],
                           "请实现函数 merge_user_scores(users, scores)。users 是用户名列表，scores 是用户名到分数的映射；返回 [{'user': 用户名, 'score': 分数或None}]。",
                           "def merge_user_scores(users, scores):\n    pass",
                           "def merge_user_scores(users, scores):\n    return [{'user': user, 'score': scores.get(user)} for user in users]",
                           [
                               {"input": [["alice", "bob"], {"alice": 95}], "expected": [{"user": "alice", "score": 95}, {"user": "bob", "score": None}]},
                               {"input": [["tom"], {"tom": 88}], "expected": [{"user": "tom", "score": 88}]},
                               {"input": [[], {}], "expected": []},
                           ], ["python", "pandas", "merge", "连接", "stage2"],
                           stage="stage2", cluster="pandas-groupby-merge-reshape", subskills=["连接思维", "映射查找", "结果整形"], question_role="bridge", prerequisites=["列表推导式", "字典 get"]),
        make_code_question("py-code7", "medium", "按月份透视销售额", "pivot_month_sales", ["records"],
                           "请实现函数 pivot_month_sales(records)。records 是字典列表，字段包含 month 和 amount；返回 month 到 amount 总和的映射。",
                           "def pivot_month_sales(records):\n    pass",
                           "def pivot_month_sales(records):\n    result = {}\n    for record in records:\n        month = record['month']\n        result[month] = result.get(month, 0) + record.get('amount', 0)\n    return result",
                           [
                               {"input": [[{"month": "2026-01", "amount": 10}, {"month": "2026-01", "amount": 5}, {"month": "2026-02", "amount": 8}]], "expected": {"2026-01": 15, "2026-02": 8}},
                               {"input": [[{"month": "2026-03", "amount": 0}]], "expected": {"2026-03": 0}},
                               {"input": [[]], "expected": {}},
                           ], ["python", "pandas", "pivot", "reshape", "stage2"],
                           stage="stage2", cluster="pandas-groupby-merge-reshape", subskills=["透视思维", "聚合", "键值累加"], question_role="bridge", prerequisites=["groupby 基础", "字典聚合"]),
        make_code_question("py-code8", "medium", "标准化日期字符串", "normalize_date_strings", ["values"],
                           "请实现函数 normalize_date_strings(values)，把形如 '2026/4/3' 的日期规范成 '2026-04-03'。",
                           "def normalize_date_strings(values):\n    pass",
                           "def normalize_date_strings(values):\n    result = []\n    for value in values:\n        year, month, day = value.replace('-', '/').split('/')\n        result.append(f'{int(year):04d}-{int(month):02d}-{int(day):02d}')\n    return result",
                           [
                               {"input": [["2026/4/3", "2026/12/25"]], "expected": ["2026-04-03", "2026-12-25"]},
                               {"input": [["2025-1-9"]], "expected": ["2025-01-09"]},
                               {"input": [[]], "expected": []},
                           ], ["python", "时间处理", "日期", "stage2"],
                           stage="stage2", cluster="time-series-and-dates", subskills=["日期清洗", "字符串解析", "格式规范化"], question_role="learn", prerequisites=["字符串处理", "列表遍历"]),
        make_code_question("py-code9", "project", "清洗并汇总分类金额", "clean_and_report", ["records"],
                           "请实现函数 clean_and_report(records)。records 为字典列表，包含 category 和 amount；忽略 amount 为 None 的记录，返回每个 category 的金额总和。",
                           "def clean_and_report(records):\n    pass",
                           "def clean_and_report(records):\n    result = {}\n    for record in records:\n        amount = record.get('amount')\n        if amount is None:\n            continue\n        category = record.get('category')\n        result[category] = result.get(category, 0) + amount\n    return result",
                           [
                               {"input": [[{"category": "A", "amount": 10}, {"category": "A", "amount": None}, {"category": "B", "amount": 5}]], "expected": {"A": 10, "B": 5}},
                               {"input": [[{"category": "X", "amount": 3}, {"category": "X", "amount": 7}]], "expected": {"X": 10}},
                               {"input": [[]], "expected": {}},
                           ], ["python", "数据清洗", "聚合", "项目", "stage2", "stage4"],
                           stage="stage2", cluster="data-cleaning-and-vectorization", subskills=["缺失值处理", "清洗", "聚合汇总"], question_role="test", prerequisites=["过滤", "聚合", "字典操作"]),
    ]
    return concept, code


def collect_focus_terms(plan_source: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ["current_stage", "today_topic", "difficulty_target", "day"]:
        value = plan_source.get(key)
        if value:
            values.append(str(value))
    for key in ["review", "new_learning", "exercise_focus", "covered", "weakness_focus", "recommended_materials", "target_segment_ids"]:
        raw = plan_source.get(key) or []
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item)
        elif raw:
            values.append(str(raw))

    extracted_priority_terms: list[str] = []
    for segment in plan_source.get("selected_segments") or []:
        if not isinstance(segment, dict):
            continue
        values.extend(str(segment.get(key) or "") for key in ["segment_id", "label", "purpose", "material_title", "material_source_name", "match_reason", "source_summary", "source_excerpt"])
        locator = segment.get("locator") if isinstance(segment.get("locator"), dict) else {}
        values.extend(str(locator.get(key) or "") for key in ["chapter", "pages"])
        values.extend(str(item) for item in locator.get("sections") or [] if item)
        values.extend(str(item) for item in segment.get("checkpoints") or [] if item)
        values.extend(str(item) for item in segment.get("target_clusters") or [] if item)
        values.extend(str(item) for item in segment.get("source_key_points") or [] if item)
        values.extend(str(item) for item in segment.get("source_examples") or [] if item)
        values.extend(str(item) for item in segment.get("source_pitfalls") or [] if item)
        if str(segment.get("source_status") or "") == "extracted":
            extracted_priority_terms.extend(str(item) for item in locator.get("sections") or [] if item)
            extracted_priority_terms.extend(str(item) for item in segment.get("source_key_points") or [] if item)
            extracted_priority_terms.extend(str(item) for item in segment.get("target_clusters") or [] if item)

    material_alignment = plan_source.get("material_alignment") if isinstance(plan_source.get("material_alignment"), dict) else {}
    values.extend(str(item) for item in material_alignment.get("selected_segment_ids") or [] if item)
    values.extend(str(item) for item in material_alignment.get("match_reasons") or [] if item)
    values.extend(str(item) for item in material_alignment.get("source_statuses") or [] if item)

    full_text = " ".join(values)
    normalized = re.sub(r"[：:，,；;、/()（）\[\]\-]+", " ", full_text.lower())
    terms = [term.strip() for term in normalized.split() if len(term.strip()) >= 2]

    extra_terms: list[str] = []
    mapping = {
        "函数": ["函数", "参数", "返回值", "functions-foundations"],
        "推导式": ["列表推导式", "推导式", "pythonic-expressions"],
        "pathlib": ["pathlib", "Path", "read_text", "write_text", "files-pathlib-json-exceptions"],
        "read_text": ["pathlib", "Path", "read_text", "files-pathlib-json-exceptions"],
        "write_text": ["pathlib", "Path", "write_text", "files-pathlib-json-exceptions"],
        "json.dumps": ["json.dumps", "json.loads", "JSON", "files-pathlib-json-exceptions"],
        "json.loads": ["json.dumps", "json.loads", "JSON", "files-pathlib-json-exceptions"],
        "文件": ["文件", "文件读写", "files-and-io"],
        "异常": ["异常", "try", "except", "traceback", "exceptions-and-debugging"],
        "调试": ["调试", "traceback", "exceptions-and-debugging"],
        "脚本": ["脚本组织", "函数化"],
        "pandas": ["pandas", "dataframe", "筛选", "pandas-filtering"],
        "numpy": ["numpy", "向量化", "data-cleaning-and-vectorization"],
        "groupby": ["groupby", "聚合", "pandas-groupby-merge-reshape"],
        "merge": ["merge", "连接", "pandas-groupby-merge-reshape"],
        "pivot": ["pivot", "reshape", "重塑", "pandas-groupby-merge-reshape"],
        "时间": ["时间处理", "日期", "时间列", "time-series-and-dates"],
        "日期": ["日期", "时间处理", "time-series-and-dates"],
        "pythonic": ["pythonic", "列表推导式", "生成器", "上下文管理器", "pythonic-expressions", "generators-and-context-managers"],
        "生成器": ["生成器", "generators-and-context-managers"],
        "上下文管理器": ["上下文管理器", "with", "generators-and-context-managers"],
        "阶段 1": ["stage1"],
        "阶段 2": ["stage2"],
        "阶段 3": ["stage3"],
        "阶段 4": ["stage4"],
    }
    full_text_lower = full_text.lower()
    for needle, mapped in mapping.items():
        if needle.lower() in full_text_lower:
            extra_terms.extend(mapped)

    ordered: list[str] = []
    for item in extracted_priority_terms + terms + extra_terms:
        cleaned = str(item or "").strip()
        if cleaned and cleaned not in ordered:
            ordered.append(cleaned)
    return ordered


def extract_difficulty_targets(plan_source: dict[str, Any], category: str) -> list[str]:
    text = str(plan_source.get("difficulty_target") or "").lower()
    if not text:
        return []
    segment = text
    if category == "concept" and "concept" in text:
        segment = text.split("concept", 1)[1]
        if "code" in segment:
            segment = segment.split("code", 1)[0]
    if category == "code" and "code" in text:
        segment = text.split("code", 1)[1]
    levels = [level for level in ["easy", "medium", "hard", "project"] if level in segment]
    ordered: list[str] = []
    for level in levels:
        if level not in ordered:
            ordered.append(level)
    return ordered


def resolve_target_stages(plan_source: dict[str, Any]) -> list[str]:
    text = " ".join(
        str(plan_source.get(key) or "")
        for key in ["current_stage", "day", "today_topic"]
    )
    stages = [stage for stage in ["stage1", "stage2", "stage3", "stage4"] if stage in text.lower()]
    if stages:
        return stages
    mapping = {
        "阶段 1": "stage1",
        "阶段 2": "stage2",
        "阶段 3": "stage3",
        "阶段 4": "stage4",
    }
    for needle, stage in mapping.items():
        if needle in text:
            return [stage]
    return []


def resolve_target_clusters(plan_source: dict[str, Any]) -> list[str]:
    focus_terms = collect_focus_terms(plan_source)
    cluster_mapping = {
        "functions-foundations": ["函数", "参数", "返回值", "列表处理"],
        "files-pathlib-json-exceptions": ["pathlib", "path", "read_text", "write_text", "json.dumps", "json.loads", "json", "try-except", "filenotfounderror", "第 10 章", "第10章"],
        "files-and-io": ["文件", "文件读写", "csv"],
        "exceptions-and-debugging": ["异常", "调试", "traceback", "try", "except"],
        "pandas-filtering": ["pandas", "筛选", "dataframe", "loc"],
        "pandas-groupby-merge-reshape": ["groupby", "merge", "pivot", "reshape", "聚合", "连接", "重塑"],
        "time-series-and-dates": ["时间", "日期", "时间处理"],
        "data-cleaning-and-vectorization": ["清洗", "向量化", "numpy", "缺失值"],
        "pythonic-expressions": ["pythonic", "推导式", "列表推导式"],
        "generators-and-context-managers": ["生成器", "上下文管理器", "with"],
    }
    matched: list[str] = []
    for cluster, needles in cluster_mapping.items():
        if any(term == cluster or any(needle in term for needle in needles) for term in focus_terms):
            matched.append(cluster)
    return matched


def score_question(item: dict[str, Any], focus_terms: list[str]) -> int:
    blob = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("question") or item.get("prompt") or ""),
            str(item.get("cluster") or ""),
            str(item.get("question_role") or ""),
            " ".join(str(tag) for tag in item.get("tags") or []),
            " ".join(str(skill) for skill in item.get("subskills") or []),
        ]
    ).lower()
    score = 0
    for term in focus_terms:
        if term and term in blob:
            score += 2 if len(term) >= 4 else 1
    role = str(item.get("question_role") or "")
    if role == "review":
        score += 1
    if role == "bridge":
        score += 1
    return score


def filter_python_questions_by_constraints(
    items: list[dict[str, Any]],
    *,
    target_stages: list[str],
    target_clusters: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    stage_pool = items
    if target_stages:
        stage_filtered = [item for item in items if str(item.get("stage") or "") in target_stages]
        if stage_filtered:
            stage_pool = stage_filtered
    cluster_pool = []
    if target_clusters:
        cluster_pool = [item for item in stage_pool if str(item.get("cluster") or "") in target_clusters]
    return cluster_pool, stage_pool


def combine_priority_pools(*pools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for pool in pools:
        for item in pool:
            item_id = str(item.get("id") or "")
            if not item_id or item_id in seen_ids:
                continue
            combined.append(item)
            seen_ids.add(item_id)
    return combined


def build_python_priority_pool(
    cluster_pool: list[dict[str, Any]],
    stage_pool: list[dict[str, Any]],
    *,
    target_clusters: list[str],
    focus_terms: list[str],
    allow_adjacent_fill: bool,
) -> tuple[list[dict[str, Any]], str]:
    if not target_clusters or not cluster_pool:
        return stage_pool, "stage-pool"
    if not allow_adjacent_fill:
        return cluster_pool, "cluster-only+strict-no-adjacent"
    adjacent_clusters = {"files-pathlib-json-exceptions": {"files-and-io", "exceptions-and-debugging"}}
    adjacent_names: set[str] = set()
    for cluster in target_clusters:
        adjacent_names.update(adjacent_clusters.get(cluster, set()))
    adjacent_pool = [
        item for item in stage_pool
        if str(item.get("cluster") or "") in adjacent_names and score_question(item, focus_terms) >= 4
    ]
    pool = combine_priority_pools(cluster_pool, adjacent_pool, stage_pool)
    return pool, "cluster-first+adjacent-fill"


def allocate_python_question_mix(
    items: list[dict[str, Any]],
    *,
    focus_terms: list[str],
    preferred_difficulties: list[str],
    limit: int,
    role_quota: list[tuple[str, int]],
) -> list[dict[str, Any]]:
    ranked: list[tuple[int, int, int, dict[str, Any]]] = []
    for index, item in enumerate(items):
        difficulty = str(item.get("difficulty") or "")
        score = score_question(item, focus_terms)
        preferred = 1 if (difficulty in preferred_difficulties if preferred_difficulties else True) else 0
        ranked.append((preferred, score, -index, item))
    ranked.sort(key=lambda entry: (entry[0], entry[1], entry[2]), reverse=True)

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for role, quota in role_quota:
        if len(selected) >= limit:
            break
        for _, _, _, item in ranked:
            if len(selected) >= limit:
                break
            if item["id"] in selected_ids:
                continue
            if str(item.get("question_role") or "") != role:
                continue
            selected.append(item)
            selected_ids.add(item["id"])
            if len([candidate for candidate in selected if str(candidate.get("question_role") or "") == role]) >= quota:
                break

    if len(selected) < limit:
        for _, _, _, item in ranked:
            if item["id"] in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(item["id"])
            if len(selected) >= limit:
                break
    return selected


def resolve_preference_quota(plan_source: dict[str, Any], *, category: str) -> list[tuple[str, int]]:
    preference_state = plan_source.get("preference_state") if isinstance(plan_source.get("preference_state"), dict) else {}
    user_model = plan_source.get("user_model") if isinstance(plan_source.get("user_model"), dict) else {}
    learning_style = normalize_string_list(preference_state.get("learning_style") or user_model.get("learning_style"))
    practice_style = normalize_string_list(preference_state.get("practice_style") or user_model.get("practice_style"))
    delivery_preference = normalize_string_list(preference_state.get("delivery_preference") or user_model.get("delivery_preference"))

    if category == "concept":
        quota = {"review": 2, "learn": 3, "bridge": 2, "test": 1}
    else:
        quota = {"review": 1, "learn": 3, "bridge": 2, "test": 1}

    if any(style in {"偏讲解", "讲解优先"} for style in learning_style):
        quota["learn"] += 1
        quota["bridge"] += 1
        quota["review"] = max(1, quota["review"] - 1)
    if any(style in {"偏练习", "练习优先"} for style in learning_style):
        quota["review"] += 1
        if category == "code":
            quota["test"] += 1
        quota["learn"] = max(1, quota["learn"] - 1)
    if any(style in {"偏项目", "项目优先"} for style in learning_style):
        quota["bridge"] += 1
        if category == "code":
            quota["test"] += 1
        quota["review"] = max(1, quota["review"] - 1)
    if any(style in {"边讲边练", "先讲后练"} for style in delivery_preference):
        quota["bridge"] += 1
    if any(style in {"先测后讲", "测试优先"} for style in delivery_preference):
        quota["review"] += 1
        quota["test"] += 1
        quota["learn"] = max(1, quota["learn"] - 1)
    if any(style in {"小代码题", "代码题优先"} for style in practice_style) and category == "code":
        quota["test"] += 1
    if any(style in {"选择/判断", "概念题优先"} for style in practice_style) and category == "concept":
        quota["review"] += 1
    if any(style in {"阅读复盘", "复盘优先"} for style in practice_style):
        quota["bridge"] += 1

    ordered_roles = ["review", "learn", "bridge", "test"]
    return [(role, quota[role]) for role in ordered_roles]


def is_initial_diagnostic_plan_source(plan_source: dict[str, Any]) -> bool:
    execution_mode = str(plan_source.get("plan_execution_mode") or "").strip().lower()
    if execution_mode in {"diagnostic", "test-diagnostic"}:
        return True
    current_stage = str(plan_source.get("current_stage") or "").strip().lower().replace("_", "-")
    if current_stage in {"diagnostic", "test-diagnostic"}:
        return True
    stop_reason = str(plan_source.get("stop_reason") or "").strip().lower().replace("_", "-")
    if stop_reason.startswith("diagnostic"):
        return True
    diagnostic_status = str(((plan_source.get("planning_state") or {}) if isinstance(plan_source.get("planning_state"), dict) else {}).get("diagnostic_status") or "").strip().lower().replace("_", "-")
    if diagnostic_status in {"in-progress", "not-started"}:
        return True
    return False


def select_python_diagnostic_questions(
    concept: list[dict[str, Any]],
    code: list[dict[str, Any]],
    plan_source: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    focus_terms = collect_focus_terms(plan_source)
    concept_pool = [item for item in concept if str(item.get("stage") or "") == "stage1" and str(item.get("cluster") or "") not in {"files-pathlib-json-exceptions"}]
    code_pool = [item for item in code if str(item.get("stage") or "") == "stage1" and str(item.get("cluster") or "") not in {"files-pathlib-json-exceptions"}]
    if not concept_pool:
        concept_pool = [item for item in concept if str(item.get("stage") or "") == "stage1"] or list(concept)
    if not code_pool:
        code_pool = [item for item in code if str(item.get("stage") or "") == "stage1" and str(item.get("cluster") or "") in {"functions-foundations", "exceptions-and-debugging", "files-and-io"}] or [item for item in code if str(item.get("stage") or "") == "stage1"] or list(code)

    concept_quota = [("review", 3), ("learn", 2), ("bridge", 2), ("test", 0)]
    code_quota = [("review", 1), ("learn", 2), ("bridge", 1), ("test", 0)]
    selected_concept = allocate_python_question_mix(
        concept_pool,
        focus_terms=focus_terms,
        preferred_difficulties=["easy", "medium"],
        limit=7,
        role_quota=concept_quota,
    )
    selected_code = allocate_python_question_mix(
        code_pool,
        focus_terms=focus_terms,
        preferred_difficulties=["easy", "medium"],
        limit=4,
        role_quota=code_quota,
    )
    selection_context = {
        "target_stages": ["stage1"],
        "target_clusters": ["functions-foundations", "exceptions-and-debugging", "files-and-io"],
        "resolved_target_clusters": resolve_target_clusters(plan_source),
        "segment_target_clusters": [],
        "cluster_selection_basis": "diagnostic-first-stage1-foundations",
        "concept_difficulties": ["easy", "medium"],
        "code_difficulties": ["easy", "medium"],
        "concept_quota": concept_quota,
        "code_quota": code_quota,
        "concept_pool_policy": "stage1-foundations-exclude-material-specific-clusters",
        "code_pool_policy": "stage1-foundations-exclude-material-specific-clusters",
        "adjacent_fill_allowed": False,
        "selection_policy": "python-diagnostic-first-foundations",
    }
    return selected_concept, selected_code, selection_context


def select_python_questions(
    concept: list[dict[str, Any]],
    code: list[dict[str, Any]],
    plan_source: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if is_initial_diagnostic_plan_source(plan_source):
        return select_python_diagnostic_questions(concept, code, plan_source)

    focus_terms = collect_focus_terms(plan_source)
    concept_difficulties = extract_difficulty_targets(plan_source, "concept")
    code_difficulties = extract_difficulty_targets(plan_source, "code")
    target_stages = resolve_target_stages(plan_source)
    resolved_target_clusters = resolve_target_clusters(plan_source)
    selected_segments = [segment for segment in plan_source.get("selected_segments") or [] if isinstance(segment, dict)]
    segment_target_clusters: list[str] = []
    for segment in selected_segments:
        for cluster in normalize_string_list(segment.get("target_clusters") or []):
            if cluster not in segment_target_clusters:
                segment_target_clusters.append(cluster)
    strict_cluster_targets = {"files-pathlib-json-exceptions"}
    strict_segment_clusters = [
        cluster for cluster in segment_target_clusters
        if cluster in strict_cluster_targets
    ]
    if strict_segment_clusters:
        target_clusters = strict_segment_clusters
        cluster_selection_basis = "strict-segment-target-clusters"
    else:
        target_clusters = resolved_target_clusters
        cluster_selection_basis = "focus-term-resolved-clusters"
    allow_adjacent_fill = not any(
        cluster in strict_cluster_targets for cluster in target_clusters
    )

    concept_cluster_pool, concept_stage_pool = filter_python_questions_by_constraints(concept, target_stages=target_stages, target_clusters=target_clusters)
    code_cluster_pool, code_stage_pool = filter_python_questions_by_constraints(code, target_stages=target_stages, target_clusters=target_clusters)

    concept_pool, concept_pool_policy = build_python_priority_pool(
        concept_cluster_pool,
        concept_stage_pool,
        target_clusters=target_clusters,
        focus_terms=focus_terms,
        allow_adjacent_fill=allow_adjacent_fill,
    )
    code_pool, code_pool_policy = build_python_priority_pool(
        code_cluster_pool,
        code_stage_pool,
        target_clusters=target_clusters,
        focus_terms=focus_terms,
        allow_adjacent_fill=allow_adjacent_fill,
    )

    concept_quota = resolve_preference_quota(plan_source, category="concept")
    code_quota = resolve_preference_quota(plan_source, category="code")

    selected_concept = allocate_python_question_mix(
        concept_pool,
        focus_terms=focus_terms,
        preferred_difficulties=concept_difficulties,
        limit=7,
        role_quota=concept_quota,
    )
    selected_code = allocate_python_question_mix(
        code_pool,
        focus_terms=focus_terms,
        preferred_difficulties=code_difficulties,
        limit=7,
        role_quota=code_quota,
    )
    selection_context = {
        "target_stages": target_stages,
        "target_clusters": target_clusters,
        "resolved_target_clusters": resolved_target_clusters,
        "segment_target_clusters": segment_target_clusters,
        "cluster_selection_basis": cluster_selection_basis,
        "concept_difficulties": concept_difficulties,
        "code_difficulties": code_difficulties,
        "concept_quota": concept_quota,
        "code_quota": code_quota,
        "concept_pool_policy": concept_pool_policy,
        "code_pool_policy": code_pool_policy,
        "adjacent_fill_allowed": allow_adjacent_fill,
        "selection_policy": "python-exact-cluster-first+source-aware-routing+preference-routing",
    }
    return selected_concept, selected_code, selection_context


def build_git_bank() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    concept = [
        {
            "id": "git-c1", "category": "concept", "type": "single", "difficulty": "easy",
            "question": "今天把 Git 理解成“快照历史系统”时，commit 最接近下面哪一项？",
            "options": ["某一时刻项目状态的一次历史快照", "只保存最后改动的那一行", "自动上传到远程服务器", "清空暂存区和历史"],
            "answer": 0,
            "explanation": "commit 是 Git 历史里的一个节点，记录某一时刻项目状态的快照。",
            "tags": ["git", "commit", "snapshot"],
        },
        {
            "id": "git-c2", "category": "concept", "type": "single", "difficulty": "easy",
            "question": "git add <file> 在最小工作流里的作用是什么？",
            "options": ["把当前文件内容放入下一次提交的候选区", "直接生成一个 commit", "把文件推送到 GitHub", "删除工作区修改"],
            "answer": 0,
            "explanation": "git add 是暂存当前内容；真正进入历史要等 git commit。",
            "tags": ["git", "add", "staging-area"],
        },
        {
            "id": "git-c3", "category": "concept", "type": "judge", "difficulty": "easy",
            "question": "判断：git add 之后如果又继续修改同一个文件，后续新修改会自动进入刚才的暂存内容。",
            "answer": False,
            "explanation": "git add 暂存的是执行 add 那一刻的内容；之后的新修改需要再次 git add。",
            "tags": ["git", "add", "working-tree", "staging-area"],
        },
        {
            "id": "git-c4", "category": "concept", "type": "multi", "difficulty": "medium",
            "question": "从修改文件到形成一次本地提交，下面哪些步骤属于最小闭环？",
            "options": ["git status 观察变化", "git add 暂存当前内容", "git commit 生成历史快照", "必须先 git push 才能 commit"],
            "answer": [0, 1, 2],
            "explanation": "最小本地闭环是修改、status 观察、add 暂存、commit 生成快照；push 是远程协作步骤。",
            "tags": ["git", "status", "add", "commit"],
        },
        {
            "id": "git-c5", "category": "concept", "type": "single", "difficulty": "medium",
            "question": "git status 对零基础学习者最重要的价值是什么？",
            "options": ["观察哪些内容在工作区、哪些内容已暂存", "自动修复冲突", "自动创建远程仓库", "永久删除未跟踪文件"],
            "answer": 0,
            "explanation": "status 是观察工具，用来判断当前修改和暂存状态。",
            "tags": ["git", "status", "working-tree", "staging-area"],
        },
        {
            "id": "git-c6", "category": "concept", "type": "judge", "difficulty": "medium",
            "question": "判断：分支可以先粗略理解成指向某个 commit 的可移动指针。",
            "answer": True,
            "explanation": "这不是分支的全部细节，但作为当前阶段心智模型是合适的。",
            "tags": ["git", "branch", "commit"],
        },
        {
            "id": "git-c7", "category": "concept", "type": "single", "difficulty": "medium",
            "question": "如果今天只学最小个人闭环，哪组命令最贴近学习重点？",
            "options": ["git status / git add / git commit / git status", "git rebase / git cherry-pick / git bisect", "git push --force / git reset --hard", "npm install / python -m venv"],
            "answer": 0,
            "explanation": "今天的重点是观察、暂存、提交，再观察状态；高级历史改写后置。",
            "tags": ["git", "workflow", "status", "add", "commit"],
        },
    ]
    return concept, []


def build_question_bank(domain: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if domain == "english":
        return build_english_bank()
    if domain == "math":
        return build_math_bank()
    if domain == "algorithm":
        return build_algorithm_bank()
    if domain == "linux":
        return build_linux_bank()
    if domain == "llm-app":
        return build_llm_app_bank()
    if domain == "python":
        return build_python_bank()
    if domain == "git":
        return build_git_bank()
    return build_general_cs_bank()


def domain_supports_code_questions(domain: str) -> bool:
    return domain not in {"linux", "english", "git"}


__all__ = [
    "build_algorithm_bank",
    "build_math_bank",
    "build_english_bank",
    "build_linux_bank",
    "build_llm_app_bank",
    "build_general_cs_bank",
    "make_python_metadata",
    "make_python_concept_question",
    "make_written_question",
    "make_code_question",
    "build_python_bank",
    "collect_focus_terms",
    "extract_difficulty_targets",
    "resolve_target_stages",
    "resolve_target_clusters",
    "score_question",
    "filter_python_questions_by_constraints",
    "combine_priority_pools",
    "build_python_priority_pool",
    "allocate_python_question_mix",
    "resolve_preference_quota",
    "select_python_questions",
    "build_git_bank",
    "build_question_bank",
    "domain_supports_code_questions",
]
