#!/usr/bin/env emacs --script

;; Script to convert Квизи.org questions to new format using fixed quiz.el
(load-file "/home/eugene/src/lewwadoo/org/org-roam/Квизи/quiz.el")

(defun quiz-convert-file ()
  "Convert the current buffer's quiz questions to new format."
  (let ((input-file "/home/eugene/src/lewwadoo/org/org-roam/Квизи/Квизи.org")
        (output-file "/home/eugene/src/lewwadoo/org/org-roam/Квизи/Квизи-converted.org"))
    
    (with-temp-buffer
      (insert-file-contents input-file)
      (org-mode)
      (goto-char (point-min))
      
      ;; Apply conversion
      (condition-case err
          (quiz-convert-categories-to-properties)
        (error 
         (message "Conversion error: %s" err)))
      
      ;; Save converted content
      (write-region (point-min) (point-max) output-file)
      (message "Conversion completed. Output saved to: %s" output-file))))

;; Run the conversion
(quiz-convert-file)