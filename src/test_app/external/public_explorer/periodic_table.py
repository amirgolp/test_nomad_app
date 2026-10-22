"""Grid positions of the elements in an 18-column periodic table.

Rows 1-7 are the periods; the lanthanides and actinides go into rows 9 and
10 below the main table, as usual.
"""

SYMBOLS = (
    'H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni '
    'Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I '
    'Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt '
    'Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr '
    'Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og'
).split()

ROWS = 10
COLUMNS = 18


def _layout():
    """(row, column) of each element, in order of atomic number."""
    yield 1, 1
    yield 1, 18
    for row in (2, 3):
        for column in (1, 2, *range(13, 19)):
            yield row, column
    for row in (4, 5):
        for column in range(1, 19):
            yield row, column
    for row, f_block_row in ((6, 9), (7, 10)):
        yield row, 1
        yield row, 2
        for column in range(3, 18):
            yield f_block_row, column
        for column in range(4, 19):
            yield row, column


POSITIONS = dict(zip(SYMBOLS, _layout(), strict=True))
