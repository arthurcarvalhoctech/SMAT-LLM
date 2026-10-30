package demo;

public class Checkout {
    public int amount = 40;
    public int used = 7;
    public int cap = 9;
    public int incoming = 0;
    public int total;
    public boolean hasRoom;

    private int round(int v) {
        return v;
    }

    public void compute() {
        total = amount + 5;
        hasRoom = used + incoming <= cap;
        total = round(total);
    }
}
