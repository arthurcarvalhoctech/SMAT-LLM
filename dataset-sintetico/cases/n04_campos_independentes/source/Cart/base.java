package demo;

public class Cart {
    public int subtotal;
    public int calls;
    public int shipping;

    public void checkout(int items, int price) {
        subtotal = items * price;
        calls++;
        shipping = 10;
    }
}
