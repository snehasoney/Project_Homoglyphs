def main():
    user​name = 7            # U+200B between user and name (invisible)
    s = "wor‍ld"             # U+200D inside the string (invisible)

    print("user​name =", user​name)
    print("string =", s)

    # Different identifier (no invisible char):
    # print(username)


if __name__ == "__main__":
    main()
















