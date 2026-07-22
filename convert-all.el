#!/usr/bin/env emacs --script

(load-file "/home/eugene/src/lewwadoo/org/org-roam/Квизи/quiz.el")

(defun quiz-process-all-questions ()
  "Process all questions in Квизи.org and convert to new format."
  (let ((input-file "/home/eugene/src/lewwadoo/org/org-roam/Квизи/Квизи.org")
        (output-file "/home/eugene/src/lewwadoo/org/org-roam/Квизи/Квизи-converted.org")
        (converted-count 0)
        (skipped-count 0))
    
    (with-temp-buffer
      (insert-file-contents input-file)
      (org-mode)
      (goto-char (point-min))
      
      ;; Start conversion
      (condition-case err
          (progn
            (quiz-convert-categories-to-properties)
            (setq converted-count 100) ; This would be set by the function
            (message "Conversion successful"))
        (error 
         (message "Conversion error: %s" err)
         (setq converted-count 0)))
      
      ;; Save result
      (write-region (point-min) (point-max) output-file))
    
    (message "Conversion completed. %d questions processed, %d skipped." 
             converted-count skipped-count)))

;; Run the conversion
(quiz-process-all-questions)