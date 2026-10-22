# Kiểm duyệt ngân hàng câu hỏi

Nguồn: `../on-thi-AICB.html`, đối chiếu bộ PDF theo báo cáo đọc tài liệu ngày 22/10/2026. Giữ nguyên ID gốc; Dxx là mã nhóm, không nhất thiết là ngày giảng thực tế.

**385 MCQ được dùng; 131 tự luận không đưa vào thi tự chấm.** Chưa tạo thêm câu hỏi ngoài giáo trình. Đây là ngân hàng ôn tập, chưa phải bộ đề được kiểm định/chứng nhận độc lập.

## Các câu tạm loại

- `D04-21`: Thiếu điều kiện đủ bằng chứng để ước lượng khớp bị che.
- `D06-06`: Gọi IoU trung bình tham chiếu là trần tuyệt đối của con người.
- `D06-30`: Mẫu số item sạch không nhất quán với tập được gài lỗi.
- `D12-22`: Chưa rõ quy ước image plane và giải phẫu trên ảnh fisheye.

## Các sửa chữa đã thực hiện

- `D01-08`: Tìm vật thể dùng bounding box gồm 4 số (x, y, w, h) + loại. Mask/polygon dùng cho segmentation; khối hộp dùng cho LiDAR 3D; danh sách điểm và cờ visibility dùng cho keypoint.
- `D02-03`: Tâm (960, 540), cỡ 192 × 216 ⇒ x1 = 864, y1 = 432, x2 = 1056, y2 = 648. Dãy (864, 432, 192, 216) là COCO [x, y, w, h], không phải hai góc.
- `D02-07`: Precision = TP/(TP+FP) = 8/10 = 0,80; Recall = TP/(TP+FN) = 8/12 ≈ 0,67.
- `D07-18`: Số lượng theo class bị hoán đổi, cho thấy class map sai. Occlusion về 0 vì định dạng YOLO detection không giữ thuộc tính này. Tổng bằng nhau không chứng minh chuyển đổi lossless; nhãn thiếu và nhãn trùng có thể bù nhau.
- `D09-13`: New error: pre-label đúng bị người sửa thành sai. Residual error: lỗi có sẵn trong pre-label nhưng chưa được người review phát hiện hoặc sửa.
- `D10-23`: Family/type/code phải nhất quán: warning_sign không thể có stop_code. Bỏ sót biển là coverage; text không đọc được là readable status; đổi type giữa các frame là temporal consistency.
- `D09-24`: Các frame liền kề thường có điểm uncertainty gần nhau, nên Top-200 có thể chọn nhiều ảnh gần trùng thay vì tăng độ phủ. Dùng diversity sampling (core-set hoặc k-means trên vector đặc trưng). Với video 30 FPS, 200 frame không thể nằm trong một giây.

D09-24: sửa cả phương án đúng để bỏ phát biểu 200 frame trong một giây ở video 30 FPS; giữ nguyên ý nghĩa chọn mẫu đa dạng và answer index.

## Nguồn và phiên bản

Mỗi câu lưu nguồn trích xuất là HTML và mã nhóm. Danh sách PDF là tài liệu đối chiếu **theo chủ đề**, không khẳng định từng câu có nguyên văn hoặc đã có số trang chính xác trong từng PDF. Không dựng số trang còn thiếu. Các phiên bản tool và số liệu được hỏi “theo bài/slide” cần hiểu trong bối cảnh khóa học.

Trang handbook 5 bị thiếu trong slide_11_2.pdf và trang cuối lặp: không khôi phục nội dung bằng phỏng đoán. Các rule có điều kiện/task-specific không được tự biến thành chuẩn chung.

Thay đổi JSON làm đổi mã phiên bản ngân hàng tự động; lịch sử lưu snapshot nên không bị chấm lại theo ngân hàng mới. BXH tách theo phiên bản để không trộn điểm khác bộ đề.

Nguồn chính thức dùng để đối chiếu thuật ngữ: [CVAT skeletons](https://docs.cvat.ai/docs/annotation/manual-annotation/shapes/skeletons/). Outside là dữ liệu annotation; Hidden chỉ điều khiển hiển thị. Nguồn này không giải quyết thay các policy chưa chốt của dự án.
