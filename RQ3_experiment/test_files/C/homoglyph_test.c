#include <stdio.h>

int main(void) {
    int раyload = 10;  // First character is Cyrillic 'р' (U+0440)
    int payload = 20;  // First character is Latin 'p' (U+0070)

    printf("раyload=%d\n", раyload);
    printf("payload=%d\n", payload);

    return 0;
}













