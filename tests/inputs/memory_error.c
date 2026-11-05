#include <stdio.h>
int main(void) {
    int values[2] = {10, 20};
    printf("%d\n", values[2]); /* Intentional out-of-bounds read for sanitizer demonstration. */
    return 0;
}
