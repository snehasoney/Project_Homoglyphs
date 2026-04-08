#include <stdio.h>

#include <stdio.h>

int main(void) {
    printf("BiDi test.....");

    // Trojan Source demo: ‮ } else { printf("ATTACK_DANGER\n"); } ‬

    if (1) {
        printf("Legitimate\n");
    }

    return 0;
}










