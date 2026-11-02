# Chuyển động giao diện

Không thêm thư viện animation; dùng CSS keyframes, Pointer Events và IntersectionObserver có sẵn trong trình duyệt.

- `src/components/HeroArtwork.tsx`: minh họa AI, nghiêng nhẹ theo chuột và nút dừng/chạy chuyển động.
- `src/hooks/useScrollReveal.ts`: cho các khối xuất hiện một lần khi vào vùng nhìn thấy; tự ngắt observer sau đó.
- `src/motion.css`: tốc độ, khoảng di chuyển, hiệu ứng hover, chuyển trang và progress bar.
- `src/App.tsx`: gắn scroll reveal và animation chuyển trang.

Các hiệu ứng chỉ thuộc lớp hiển thị, không thay đổi service/API hoặc thuật toán matching. Thanh điểm chỉ chuyển động đến giá trị được truyền vào, không tạo điểm số mới.

Hệ thống tắt chuyển động nếu người dùng bật Reduce Motion trong thiết bị. Nút “모션 일시정지” dừng vòng lặp trang trí ở hero. Touch không dùng hiệu ứng nghiêng theo chuột.
