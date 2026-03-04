import re

fp = r'finance-app-frontend\src\pages\Insights.js'
txt = open(fp, 'r', encoding='utf-8').read()

# Find the persona+date wrapper div and replace with just date input
# Look for the outer div wrapping both controls
start_marker = '                <div className="flex flex-col sm:flex-row items-end sm:items-center gap-3">'
end_marker = '                </div>\n            </div>\n        )})'

idx_start = txt.find(start_marker)
print(f"start_marker at: {idx_start}")

if idx_start == -1:
    # Try alternative - just find the support_agent icon and its surrounding div
    idx = txt.find('support_agent')
    print(f"support_agent at: {idx}")
    print(repr(txt[idx-150:idx+500]))
else:
    # Find the matching end - we need to count divs
    pos = idx_start + len(start_marker)
    depth = 1
    while depth > 0 and pos < len(txt):
        next_open = txt.find('<div', pos)
        next_close = txt.find('</div>', pos)
        if next_close == -1:
            break
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 4
        else:
            depth -= 1
            if depth == 0:
                end_pos = next_close + len('</div>')
                break
            pos = next_close + 6

    old_block = txt[idx_start:end_pos]
    print("OLD BLOCK:")
    print(repr(old_block[:400]))

    new_block = '''                <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800 p-1.5 rounded-lg">
                    <span className="material-icons-round text-slate-400 ml-1 text-sm">calendar_today</span>
                    <input
                        type="month"
                        value={month}
                        onChange={(e) => setMonth(e.target.value)}
                        className="bg-transparent border-none text-sm font-bold text-slate-700 dark:text-slate-200 focus:ring-0 cursor-pointer pr-2"
                    />
                </div>'''

    new_txt = txt[:idx_start] + new_block + txt[end_pos:]
    open(fp, 'w', encoding='utf-8').write(new_txt)
    print("Done! Replaced persona block with just date input.")
