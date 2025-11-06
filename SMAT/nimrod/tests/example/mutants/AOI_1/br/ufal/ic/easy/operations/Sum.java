package br.ufal.ic.easy.operations;

public class Sum implements Operation {

    public int impacted(int a, int b) {
        int c = 0;
        int d = 0;

        while (d < 10) {
            c += (a + this.execute(c, b));
            d++;
        }

        return c;
    }

    public int execute(int a, int b) {
        return a + b++;
    }
}