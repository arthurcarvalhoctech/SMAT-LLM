package demo;

public class Flags {
    public int x = 0;
    public int z;
    public int y = 0;

    public void run() {
        if (x + y > 1) {
            z = 1;
        } else {
            z = 0;
        }
    }
}
