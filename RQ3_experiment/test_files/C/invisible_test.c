#include <stdio.h>

int main(void) {
    int user​name = 7;          // U+200B between user and name (invisible)
    const char *s = "wor‍ld";   // U+200D inside the string (invisible)

    printf("user​name=%d\n", user​name);
    printf("string=%s\n", s);

    // This is a DIFFERENT identifier (no invisible char):
    // printf("username=%d\n", username);

    return 0;
}















