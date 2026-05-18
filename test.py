from itertools import product

# Известные коды
codes = {
    'В': '110',
    'З': '01',
    'И': '000'
}

letters = ['А', 'Д', 'О']

# Проверка условия Фано
def fano(code_list):
    for a in code_list:
        for b in code_list:
            if a != b and b.startswith(a):
                return False
    return True

# Все уже занятые коды
used = set(codes.values())

best_len = 10**9
best_codes = None

# Перебираем возможные двоичные слова длиной 1..5
all_codes = []
for l in range(1, 6):
    for p in product('01', repeat=l):
        s = ''.join(p)
        if s not in used:
            all_codes.append(s)

# Подбираем коды для А, Д, О
for a in all_codes:
    for d in all_codes:
        for o in all_codes:
            new_codes = list(codes.values()) + [a, d, o]

            # Все коды должны быть различны
            if len(set(new_codes)) != 6:
                continue

            # Проверяем условие Фано
            if not fano(new_codes):
                continue

            # Длина кодирования слова АВИАЗАВОД
            total = (
                len(a) +      # А
                len(codes['В']) +
                len(codes['И']) +
                len(a) +      # А
                len(codes['З']) +
                len(a) +      # А
                len(codes['В']) +
                len(o) +      # О
                len(d)        # Д
            )

            if total < best_len:
                best_len = total
                best_codes = {'А': a, 'Д': d, 'О': o}

print("Минимальная длина:", best_len)
print("Коды:", best_codes)