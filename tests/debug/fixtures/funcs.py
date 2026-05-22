def inner(n):
    return n + 1


def outer():
    a = 1
    b = inner(a)
    return b


outer()
