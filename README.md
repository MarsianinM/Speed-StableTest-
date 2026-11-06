# SpetTestMy

Портативна консольна утиліта для Windows: окремий замір **швидкості** і окрема перевірка **стабільності** каналу. Запуск з флешки без встановленого Python на цільовому ПК.

Документація: [docs/TZ.md](docs/TZ.md), [docs/TODO.md](docs/TODO.md).

## Розробка

Потрібен Python 3.11+.

```powershell
cd SpetTestMy
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Запуск:

```powershell
python -m spettest speed
python -m spettest stable
python -m spettest stable 120
```

Або без editable-install:

```powershell
$env:PYTHONPATH = "src"
python -m spettest speed
```

## Портативні ярлики

Шаблони для флешки: папка [`portable/`](portable/) — `Швидкість.cmd`, `Стабільність.cmd`, `README.txt`.  
Працюють після збірки exe (етап 5): потрапляють у `dist/SpetTest/` поруч із `SpetTest.exe`.

## Збірка для флешки

```powershell
.\scripts\build.ps1
```

Результат: `dist/SpetTest/` (`SpetTest.exe`, `Швидкість.cmd`, `Стабільність.cmd`, `README.txt`).  
Скопіюйте **всю** цю папку на флешку. Режим `--onefile` заборонений.
